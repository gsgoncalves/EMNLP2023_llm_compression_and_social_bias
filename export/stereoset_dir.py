
import argparse
import json
import os
import re
import sys

import pandas as pd

thisdir = os.path.dirname(os.path.realpath(__file__))
parser = argparse.ArgumentParser(description="Export StereoSet results.")
parser.add_argument(
    "--persistent_dir",
    action="store",
    type=str,
    default=os.path.realpath(os.path.join(thisdir, "..")),
    help="Directory where all persistent data will be stored.",
)
parser.add_argument(
    "--bias_type",
    action="store",
    type=str,
    choices=["gender", "race", "religion", "profession", "overall"],
    default="gender",
    help="Which type of bias to export results for.",
)
parser.add_argument(
    "--model_type",
    action="store",
    type=str,
    #choices=["bert", "albert", "roberta", "gpt2"],
    help="What model type to export results for.",
)


def _parse_experiment_id(experiment_id):
    model = None
    model_name_or_path = None
    bias_type = None
    seed = None
    quant_type = None
    quant_prec = None

    items = experiment_id.split("_")[1:]
    for item in items:
        splt = item.split("-")
        if len(splt) > 2:
            id_, val = splt[0], '-'.join(splt[1:])
        else:
            id_, val = splt[0], splt[1]
        #id_, val = item[:1], item[2:]
        if id_ == "m":
            model = val
        elif id_ == "c":
            model_name_or_path = val
        elif id_ == "t":
            bias_type = val
        elif id_ == "s":
            seed = int(val)
        elif id_ == "qt":
            quant_type = val
        elif id_ == "qp":
            quant_prec = val
        elif id_ == "rev":
            quant_prec = val
        else:
            raise ValueError(f"Unrecognized ID {id_}.")

    return model, model_name_or_path, bias_type, seed, quant_type, quant_prec


def _label_model_type(row):
    if "Bert" in row["model"]:
        return "bert"
    elif "Albert" in row["model"]:
        return "albert"
    elif "Roberta" in row["model"]:
        return "roberta"
    else:
        return "gpt2"


def _pretty_model_name(row):
    pretty_name_mapping = {
        "BertForMaskedLM": "BERT",
        "QuantizedBertModelMaskedLM": "BERT Quantized",
        "DistilBertForMaskedLM": "Distil BERT",
        "SentenceDebiasBertForMaskedLM": r"\, + \textsc{SentenceDebias}",
        "INLPBertForMaskedLM": r"\, + \textsc{INLP}",
        "CDABertForMaskedLM": r"\, + \textsc{CDA}",
        "DropoutBertForMaskedLM": r"\, + \textsc{Dropout}",
        "SelfDebiasBertForMaskedLM": r"\, + \textsc{Self-Debias}",
        "AlbertForMaskedLM": "ALBERT",
        "SentenceDebiasAlbertForMaskedLM": r"\, + \textsc{SentenceDebias}",
        "INLPAlbertForMaskedLM": r"\, + \textsc{INLP}",
        "CDAAlbertForMaskedLM": r"\, + \textsc{CDA}",
        "DropoutAlbertForMaskedLM": r"\, + \textsc{Dropout}",
        "SelfDebiasAlbertForMaskedLM": r"\, + \textsc{Self-Debias}",
        "RobertaForMaskedLM": "RoBERTa",
        "QuantizedRobertaModelMaskedLM": "RoBERTa Quantized",
        "DistilRobertaForMaskedLM": "Distil RoBERTa",
        "SentenceDebiasRobertaForMaskedLM": r"\, + \textsc{SentenceDebias}",
        "INLPRobertaForMaskedLM": r"\, + \textsc{INLP}",
        "CDARobertaForMaskedLM": r"\, + \textsc{CDA}",
        "DropoutRobertaForMaskedLM": r"\, + \textsc{Dropout}",
        "SelfDebiasRobertaForMaskedLM": r"\, + \textsc{Self-Debias}",
        "GPT2LMHeadModel": "GPT-2",
        "SentenceDebiasGPT2LMHeadModel": r"\, + \textsc{SentenceDebias}",
        "INLPGPT2LMHeadModel": r"\, + \textsc{INLP}",
        "CDAGPT2LMHeadModel": r"\, + \textsc{CDA}",
        "DropoutGPT2LMHeadModel": r"\, + \textsc{Dropout}",
        "SelfDebiasGPT2LMHeadModel": r"\, + \textsc{Self-Debias}",
    }

    return pretty_name_mapping[row["model"]]


def _get_baseline_metric(df, model_type, metric="stereotype_score"):
    model_type_to_baseline = {
        "bert": "BertForMaskedLM",
        "albert": "AlbertForMaskedLM",
        "roberta": "RobertaForMaskedLM",
        "gpt2": "GPT2LMHeadModel",
    }
    baseline = model_type_to_baseline[model_type]
    return df[df["model"] == baseline][metric].values[0]


def _pretty_stereotype_score(row, baseline_metric):
    baseline_diff = abs(baseline_metric - 50)
    debias_diff = abs(row["stereotype_score"] - 50)

    if debias_diff == baseline_diff:
        return f"{row['stereotype_score']:.2f}"
    elif debias_diff < baseline_diff:
        return (
            r"\da{"
            + f"{baseline_diff - debias_diff:.2f}"
            + r"} "
            + f"{row['stereotype_score']:.2f}"
        )
    else:
        return (
            r"\ua{"
            + f"{debias_diff - baseline_diff:.2f}"
            + r"} "
            + f"{row['stereotype_score']:.2f}"
        )


def _pretty_language_model_score(row, baseline_metric):
    if baseline_metric == row["language_model_score"]:
        return f"{row['language_model_score']:.2f}"
    elif row["language_model_score"] < baseline_metric:
        return (
            r"\dab{"
            + f"{abs(baseline_metric - row['language_model_score']):.2f}"
            + r"} "
            + f"{row['language_model_score']:.2f}"
        )
    else:
        return (
            r"\uag{"
            + f"{abs(row['language_model_score'] - baseline_metric):.2f}"
            + r"} "
            + f"{row['language_model_score']:.2f}"
        )

def process_results(args, results, filename):
    records = []
    for experiment_id in results:
        model, model_name_or_path, bias_type, seed, quant_type, quant_prec = _parse_experiment_id(filename)

        # Skip records we don't want to export.
        if bias_type is not None and bias_type != args.bias_type:
            continue

        stereotype_score = results[experiment_id]["intrasentence"][args.bias_type][
            "SS Score"
        ]
        language_model_score = results[experiment_id]["intrasentence"]["overall"][
            "LM Score"
        ]

        # Re-format the data.
        records.append(
            {
                "experiment_id": experiment_id,
                "model": model,
                "model_name_or_path": model_name_or_path,
                "bias_type": bias_type,
                "seed": seed,
                "stereotype_score": stereotype_score,
                "language_model_score": language_model_score,
                "quant_type": quant_type,
                "quant_prec": quant_prec,
            }
        )

    df = pd.DataFrame.from_records(records)

    # Label model type (e.g., "bert").
    df["model_type"] = df.apply(lambda row: _label_model_type(row), axis=1)

    # Get pretty model name.
    df["pretty_model_name"] = df.apply(lambda row: _pretty_model_name(row), axis=1)
    # add quantization type to model name
    df["pretty_model_name"] = df['pretty_model_name'].fillna('') + ' ' + df['quant_type'].fillna('')
    # add quantization prec to model name
    df["pretty_model_name"] = df['pretty_model_name'].fillna('') + ' ' + df['quant_prec'].fillna('')

    # Filter to subset of results.
    df = df[df["model_type"] == args.model_type]

    baseline_stereotype_score = _get_baseline_metric(
        df, args.model_type, metric="stereotype_score"
    )
    baseline_language_model_score = _get_baseline_metric(
        df, args.model_type, metric="language_model_score"
    )

    # Get pretty metric values.
    df["pretty_stereotype_score"] = df.apply(
        lambda row: _pretty_stereotype_score(row, baseline_stereotype_score), axis=1
    )
    df["pretty_language_model_score"] = df.apply(
        lambda row: _pretty_language_model_score(row, baseline_language_model_score),
        axis=1,
    )

    # Only include results for the first seed.
    df = df[(df["seed"] == 0) | (df["seed"].isnull())]

    # To get proper ordering.
    df = df.sort_values(by="pretty_model_name")

    print(df)

    with pd.option_context("max_colwidth", 1000):
        print(
            df.to_latex(
                float_format="%.2f",
                columns=[
                    "pretty_model_name",
                    "pretty_stereotype_score",
                ],
                index=False,
                escape=False,
            )
        )

    os.makedirs(f"{args.persistent_dir}/tables", exist_ok=True)
    with pd.option_context("max_colwidth", 1000):
        with open(
                f"{args.persistent_dir}/tables/stereoset_m-{args.model_type}_t-{args.bias_type}.tex",
                "w",
        ) as f:
            f.write(
                df.to_latex(
                    float_format="%.2f",
                    columns=[
                        "pretty_model_name",
                        "pretty_stereotype_score",
                    ],
                    index=False,
                    escape=False,
                )
            )

if __name__ == "__main__":
    args = parser.parse_args()

    print("Exporting StereoSet results:")
    print(f" - persistent_dir: {args.persistent_dir}")
    print(f" - bias_type: {args.bias_type}")

    # Load the StereoSet model scores.
    #with open(f"{args.persistent_dir}/results/stereoset/results.json", "r") as f:
    #    results = json.load(f)

    dir = f"{args.persistent_dir}/results/stereoset/"
    for filename in os.listdir(dir):
        filepath = os.path.join(dir, filename)
        # checking if it is a file
        if os.path.isfile(filepath):
            with open(filepath, "r") as f:
                results = json.load(f)
                process_results(args, results, filename)
    sys.exit(0)
