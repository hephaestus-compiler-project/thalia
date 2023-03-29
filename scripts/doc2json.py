#! /usr/bin/env python3
import argparse
import os
import sys

from docparser.java import JavaAPIDocConverter
from docparser.kotlin import KotlinAPIDocConverter
from docparser.scala import ScalaAPIDocConverter


def preprocess_args(args):
    # Some pre-processing to create the output directory.

    if not os.path.isdir(args.output):
        try:
            os.makedirs(args.output, exist_ok=True)
        except IOError as e:
            print(e)
            sys.exit(0)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--language",
        default="java",
        choices=["java", "kotlin", "scala"],
        help="Language associated with the given API docs"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Directory to output JSON files"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Input directory of API docs"
    )
    parser.add_argument(
        "--jdk-docs",
        action="store_true",
        help="Indicate whether the documentation is related to JDK"
    )
    return parser.parse_args()


CONVERTERS = {
    "java": JavaAPIDocConverter,
    "kotlin": KotlinAPIDocConverter,
    "scala": ScalaAPIDocConverter,
}


def main():
    args = get_args()
    preprocess_args(args)
    converter = CONVERTERS.get(args.language)(args)
    converter.process(args)


if __name__ == '__main__':
    main()
