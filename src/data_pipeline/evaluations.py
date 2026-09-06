import json
import os

from difflib import SequenceMatcher

def string_similarity(a, b):
    """
    Uses SequenceMatcher to calculate similarity ratio between two strings.
    Algorithm is based on Ratcliff/Obershelp pattern recognition. (https://typesense.org/learn/fuzzy-string-matching-python/)

    Note: string_similarity(a, b) is not the same as string_similarity(b, a).

    Args:
        a (str): First string.
        b (str): Second string.

    Returns:
        float: Similarity ratio between the two strings.
    """

    return SequenceMatcher(None, a, b).ratio()

def evaluate_json(gt_json, llm_json):
    """
    Evaluate JSON function for a single ground truth and LLM pair.

    Args:
        gt_json (dict): Ground truth JSON data.
        llm_json (dict): LLM JSON data.

    Returns:
        dict: Evaluation results for each field in the JSON data.
    """

    field_results = {}
    for key in gt_json.keys():
        gt_value = gt_json.get(key)
        llm_value = llm_json.get(key)

        if isinstance(gt_value, str) and isinstance(llm_value, str):
            similarity = string_similarity(gt_value.lower(), llm_value.lower())
            field_results[key] = similarity

        elif isinstance(gt_value, list) and isinstance(llm_value, list):
            if len(gt_value) == len(llm_value):
                similarities = []
                for i, (gt_item, llm_item) in enumerate(zip(gt_value, llm_value)):
                    if isinstance(gt_item, dict) and isinstance(llm_item, dict):
                        for sub_key in gt_item.keys():
                            nested_similarity = string_similarity(str(gt_item[sub_key]).lower(), str(llm_item[sub_key]).lower())
                            similarities.append(nested_similarity)
                    else:
                        item_similarity = string_similarity(str(gt_item).lower(), str(llm_item).lower())
                        similarities.append(item_similarity)
                field_results[key] = sum(similarities) / len(similarities) if similarities else 1.0
            else:
                field_results[key] = 0.0  # Array length mismatch

        else:
            field_results[key] = 1.0 if gt_value == llm_value else 0.0

    return field_results

def aggregate_results(gt_llm_pairs):
    """
    Aggregate results function for multiple ground truth and LLM pairs.

    Args:
        gt_llm_pairs (list): List of tuples containing ground truth and LLM JSON data.

    Returns:
        dict: Averaged evaluation results for each field in the JSON data.
    """

    # Initialize aggregate scores dictionary
    aggregate_scores = {key: [] for key in gt_llm_pairs[0][0].keys()}  # Assumes all JSONs have the same keys

    # Evaluate each ground truth and LLM JSON pair
    for gt_json, llm_json in gt_llm_pairs:
        result = evaluate_json(gt_json, llm_json)
        for key, score in result.items():
            aggregate_scores[key].append(score)

    # Calculate average score for each field
    averaged_results = {key: sum(scores) / len(scores) for key, scores in aggregate_scores.items()}
    return averaged_results

def remove_duplicates(results):
    """
    Remove duplicates from a list of dictionaries.

    Args:
        results (list): List of dictionaries.

    Returns:
        list: List of unique dictionaries.
    """

    seen = set()
    unique_results = []

    for result in results:
        # Convert dictionary to a JSON string, which is hashable
        result_str = json.dumps(result, sort_keys=True)

        if result_str not in seen:
            seen.add(result_str)
            unique_results.append(result)

    return unique_results

def process_results(filepaths, prompt, json_schema, title_for_llm_experiment, results_path):
    gt_llm_pairs = []
    for filepath in filepaths:
        gt_json_path = os.path.dirname(filepath) + "\\meeting_agenda.json"
        llm_json_path = os.path.dirname(filepath) + "\\llm_meeting_agenda.json"

        if os.path.exists(gt_json_path) and os.path.exists(llm_json_path):
            with open(gt_json_path, "r", encoding="utf-8") as f:
                gt_json = json.load(f)

            with open(llm_json_path, "r", encoding="utf-8") as f:
                llm_json = json.load(f)
            # make tuple of gt and llm jsons
            gt_llm_tuple = (gt_json, llm_json)
            gt_llm_pairs.append(gt_llm_tuple)

    averaged_results = aggregate_results(gt_llm_pairs)
    print("Result:", json.dumps(averaged_results, indent=2))

    # print average of all keys in result
    average = sum(averaged_results.values()) / len(averaged_results)
    print("Average:", average)

    # save results in a file along with the prompt, gt and llm jsons, individual results and average
    results = [{
        "title": title_for_llm_experiment,
        "prompt": prompt,
        "schema": json_schema,
        "gt_llm_pairs": gt_llm_pairs,
        "individual_results": averaged_results,
        "average": average
    }]

    # if file exists, load the existing results and append the new results
    # else create a new file with the results
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            all_results = json.load(f)
        all_results.extend(results)
    else:
        all_results = results

    # remove duplicates from the results
    all_results = remove_duplicates(all_results)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    return all_results
