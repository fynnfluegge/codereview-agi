import json
import os
from typing import Any, Dict
import gitreview_gpt.prompt as prompt
import gitreview_gpt.formatter as formatter
import gitreview_gpt.utils as utils
import gitreview_gpt.request as request
from gitreview_gpt.treesitter.treesitter import (
    Treesitter,
    TreesitterNode,
    get_source_from_node,
)


# Retrieve review from openai completions api
# Process response and send repair request if json has invalid format
def request_review(
    api_key, code_to_review, gpt_model, file_name=None
) -> Dict[str, Any] | None:
    max_tokens = gpt_model.value - utils.count_tokens(
        json.dumps(prompt.get_review_prompt(code_to_review, gpt_model.value, gpt_model))
    )
    payload = prompt.get_review_prompt(code_to_review, max_tokens, gpt_model)

    spinner_text = "🔍 Reviewing"
    if file_name is not None:
        spinner_text += f" {utils.get_bold_text(file_name)}"
    spinner_text += "..."

    review_result = request.send_request(api_key, payload, spinner_text)
    if not review_result:
        return None
    try:
        review_json = formatter.parse_review_result(review_result)
    except ValueError:
        try:
            # Try to parse review result from marldown code block
            review_json = formatter.parse_review_result(
                formatter.extract_content_from_markdown_code_block(review_result)
            )
        except ValueError:
            try:
                # Try to repair truncated review result
                review_json = formatter.parse_review_result(
                    utils.repair_truncated_json(review_result)
                )
            except ValueError as e:
                try:
                    print("Review result has invalid format. It will be repaired.")
                    payload = prompt.get_review_repair_prompt(
                        review_result, e, max_tokens, gpt_model
                    )
                    review_result = request.send_request(
                        api_key, payload, "🔧 Repairing..."
                    )
                    review_json = formatter.parse_review_result(
                        formatter.extract_content_from_markdown_code_block(
                            review_result
                        )
                    )
                except ValueError:
                    print("💥 Review result could not be repaired.")
                    print(review_result)
                    print(
                        "Feel free to create an issue at https://github.com/fynnfluegge/codereview-agi/issues"
                    )
                    return None

    return review_json


# Retrieve code changes from openai completions api
# for one specific file with the related review
def apply_review(
    api_key,
    absolute_file_path,
    review_json,
    selection_marker_chunks: Dict,
    gpt_model,
):
    try:
        with open(absolute_file_path, "r") as file:
            file_name = os.path.basename(file.name)
            file_content = file.read()
            file_extension = utils.get_file_extension(file_name)
            programming_language = utils.get_programming_language(file_extension)
            treesitter_parser = Treesitter.create_treesitter(programming_language)
            treesitterNodes: list[TreesitterNode] = treesitter_parser.parse(
                file_content.encode()
            )
            payload = {
                "code": file_content,
                "reviews": formatter.get_review_suggestions_per_file_payload_from_json(
                    review_json
                ),
            }
            prompt_payload = prompt.get_apply_review_for_file_prompt(
                file_content,
                json.dumps(payload["reviews"]),
                gpt_model.value,
                programming_language,
                gpt_model,
            )
            tokens = utils.count_tokens(json.dumps(prompt_payload))
            # tokens for file content and review suggestions are greater than threshold
            # split requests into code chunks by selection markers
            if tokens > gpt_model.value / 2 and selection_marker_chunks is not None:
                # initialize reviewed code for applying code changes later a tonce
                reviewed_code_chunks = []

                # create line number stack for  merging code chunk with line numbers
                line_number_stack = []
                for line_number in reversed(review_json.keys()):
                    line_number_stack.append(utils.parse_string_to_int(line_number))

                code_chunks_to_review = []

                # prompt offset tokens
                prompt_tokens = utils.count_tokens(
                    json.dumps(
                        prompt.get_apply_review_for_file_prompt(
                            "",
                            "",
                            gpt_model.value,
                            programming_language,
                            gpt_model,
                        )
                    )
                )

                # iterate over code chunks by selection markers
                # and merge them with review suggestions by line numbers
                for selection_marker in selection_marker_chunks.keys():
                    print("selection_marker " + selection_marker)
                    print("line_number_stack")
                    print(line_number_stack)
                    code_chunk = selection_marker_chunks[selection_marker]
                    # if there are no more line numbers in stack,
                    # there are no more review suggestions, break loop
                    if not line_number_stack:
                        break

                    # merge code chunk with suggestions by line numbers
                    selection_marker_code_chunks_with_suggestions = (
                        formatter.parse_apply_review_per_code_hunk(
                            code_chunk,
                            review_json,
                            line_number_stack,
                        )
                    )

                    for obj in selection_marker_code_chunks_with_suggestions:
                        print(obj["suggestions"])
                        print(obj["code"].code)
                        print(obj["code"].start_line)
                        print(obj["code"].end_line)

                    merged_suggestions = {}
                    for obj in selection_marker_code_chunks_with_suggestions:
                        for line_number, feedback in obj["suggestions"].items():
                            merged_suggestions[line_number] = feedback

                    print(merged_suggestions)

                    code = None
                    for node in treesitterNodes:
                        if node.name in selection_marker:
                            print("node name " + node.name.__str__())
                            node_source = get_source_from_node(node.node)
                            start_line = utils.get_start_line_number(
                                file_content, node_source.split("\n")[0]
                            )
                            code = utils.add_line_numbers(node_source, start_line)
                            break

                    payload = {
                        "code": code,
                        "suggestions": merged_suggestions,
                    }

                    # print(payload)

                    # there are review suggestions in that code chunk
                    if code and merged_suggestions:
                        chunk_tokens = (
                            utils.count_tokens(json.dumps(payload)) + prompt_tokens
                        )
                        # if chunk tokens are smaller than threshold
                        # add chunk to code chunks to review
                        if chunk_tokens <= gpt_model.value / 2:
                            print("Payload added")
                            code_chunks_to_review.append(payload)
                        else:
                            print("Payload not added")
                            # code chunk tokens are greater than threshold
                            # skip since results are not reliable
                            pass

                if code_chunks_to_review:
                    code_chunk_count = code_chunks_to_review.__len__()
                    for index, chunk in enumerate(code_chunks_to_review, start=1):
                        reviewed_code_chunk = request_review_changes(
                            chunk,
                            api_key,
                            gpt_model,
                            programming_language,
                            index,
                            code_chunk_count,
                            file_name,
                        )
                        reviewed_code_chunks.append(
                            {
                                "original_code": chunk["code"],
                                "reviewed_code": utils.extract_content_from_markdown_code_block(
                                    reviewed_code_chunk
                                ),
                            }
                        )

                file.close()

                print(
                    "number of reviewed code chunks "
                    + reviewed_code_chunks.__len__().__str__()
                )
                for reviewed_code_chunk in reviewed_code_chunks:
                    reviewed_code = reviewed_code_chunk["reviewed_code"]
                    original_code = reviewed_code_chunk["original_code"]
                    # print("-------------- Reviewed Code --------------")
                    # print(reviewed_code)
                    utils.write_code_snippet_to_file(
                        absolute_file_path, original_code, reviewed_code
                    )

                print(
                    "✅ Successfully applied review changes to "
                    f"{utils.get_bold_text(os.path.basename(absolute_file_path))}"
                    "\n"
                    "Note: The changes have been applied iteratively "
                    "due to the large amount of changes. "
                    "There might be syntax errors in the code. "
                    f"Consider using the {utils.get_bold_text('--gpt4')} flag."
                )

            # tokens for file content and review suggestions are less than threshold
            # send request for file content and review suggestions
            else:
                max_completions_tokens = gpt_model.value - tokens
                reviewed_git_diff = request.send_request(
                    api_key,
                    prompt.get_apply_review_for_file_prompt(
                        file_content,
                        json.dumps(payload["reviews"]),
                        max_completions_tokens,
                        programming_language,
                        gpt_model,
                    ),
                    f"🔧 Applying changes to {utils.get_bold_text(file_name)}...",
                )
                reviewed_git_diff = formatter.extract_content_from_markdown_code_block(
                    reviewed_git_diff
                )
                file.close()
                with open(absolute_file_path, "w") as file:
                    if reviewed_git_diff:
                        file.write(reviewed_git_diff)
                        print(
                            "✅ Successfully applied review changes to "
                            f"{utils.get_bold_text(file_name)}"
                        )

    except FileNotFoundError:
        print(f"💥 File '{absolute_file_path}' not found.")
    except IOError:
        print(f"💥 Error reading file '{absolute_file_path}'.")
    except ValueError as e:
        print(f"💥 Error while applying review changes for file {absolute_file_path}.")
        print(e)
    return None


def request_review_changes(
    code_chunk_with_suggestions,
    api_key,
    gpt_model,
    programming_language,
    current_step,
    total_steps,
    file_name,
):
    message_tokens = utils.count_tokens(
        json.dumps(
            prompt.get_apply_review_for_treesitter_node_prompt(
                code_chunk_with_suggestions["code"],
                json.dumps(code_chunk_with_suggestions["suggestions"]),
                gpt_model.value,
                programming_language,
                gpt_model,
            )
        )
    )
    return request.send_request(
        api_key,
        prompt.get_apply_review_for_treesitter_node_prompt(
            code_chunk_with_suggestions["code"],
            json.dumps(code_chunk_with_suggestions["suggestions"]),
            gpt_model.value - message_tokens,
            programming_language,
            gpt_model,
        ),
        "🔧 Applying changes to "
        + f"{utils.get_bold_text(file_name)}... {current_step}/{total_steps}",
    )
