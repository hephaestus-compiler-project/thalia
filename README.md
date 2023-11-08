Thalia
======

Thalia is a testing framework for validating static typing procedures
in compilers via an API-driven program synthesis approach.
The idea is to synthesize type-intensive but
small and well-typed programs
by leveraging and combining
application programming interfaces (APIs)
derived from existing software libraries.

Thalia is built on top of
[Hephaestus](https://github.com/hephaestus-compiler-project/hephaestus).
Currently, Thalia is able to produce test cases written in four
popular programming languages: Java, Scala, Kotlin, and Groovy.


## API-driven Program Synthesis

At the high level,
Thalia's appoach works as follows.
The input is an API,
which is modeled as an API graph,
a structure that captures
the dependencies and relations among
API components.
Then,
Thalia proceeds with the concept of _API enumeration_,
which systematically explores all possible invocations
of the encompassed API components
through _unique_ typing patterns.
A typing pattern is
a sequence of types
that corresponds to _abstract typed expressions_.
Conceptually,
an abstract typed expression represents
a combination of types
used to invoke a particular API entity (e.g, method).
An abstract expression can be
either well-typed or ill-typed
with regards to the type signature of
the corresponding API component.
Then,
Thalia yields well-typed or ill-typed programs
by concretizing each abstract-typed expression
into a concrete one written
in a reference intermediate language.
To do so,
it examines the API graph to find type inhabitants 
by enumerating the set of paths
that reach a specific type node.

As an optional step,
Thalia employs
the type erasure process
whose purpose is to remove the type arguments
of polymorphic calls,
while maintaining the type correctness of the
The final step is to employ
language-specific translators that
transform an expression in the intermediate language
into a source file written in an actual
language (e.g., Scala).
Ultimately,
the generated source files are given
as input to the compiler under test,
whose output is checked against
the given oracle for potential bugs.
In particular,
we expect the compiler to accept
the programs derived from well-typed typing sequences,
and reject those
that come from ill-typed ones.

# Requirements

* Python: 3.8+

# Getting Started

## Install

```
pip install .
```

## Run tests

To run `thalia` tests, execute the following command:

```
python -m pytest
```

The output of the previous command should be similar to the following:

```
tests/test_api_graph.py::test1 PASSED                                                   [  0%]
tests/test_api_graph.py::test2 PASSED                                                   [  0%]
...
tests/test_use_analysis.py::test_program6 PASSED                                        [ 99%]
tests/test_use_analysis.py::test_program7 PASSED                                        [ 99%]
tests/test_use_analysis.py::test_program8 PASSED                                        [100%]

===================================== 232 passed in 0.46s =====================================
```

## Usage

```
usage: thalia [-h] [-g {base,api}] [--api-doc-path API_DOC_PATH] [-s SECONDS] [-i ITERATIONS] [--api-rules API_RULES] [--library-path LIBRARY_PATH]
              [--max-conditional-depth MAX_CONDITIONAL_DEPTH] [--erase-types] [--inject-type-error] [--disable-expression-cache] [--path-search-strategy {shortest,ksimple}]
              [-t TRANSFORMATIONS] [--batch BATCH] [-b BUGS] [-n NAME] [-T [{TypeErasure} [{TypeErasure} ...]]] [--transformation-schedule TRANSFORMATION_SCHEDULE] [-R REPLAY] [-e] [-k]
              [-S] [-w WORKERS] [-d] [-r] [-F LOG_FILE] [-L] [-N] [--language {kotlin,groovy,java,scala}] [--max-type-params MAX_TYPE_PARAMS] [--max-depth MAX_DEPTH] [-P]
              [--timeout TIMEOUT] [--cast-numbers] [--disable-function-references] [--disable-use-site-variance] [--disable-contravariance-use-site] [--disable-bounded-type-parameters]
              [--disable-parameterized-functions] [--disable-sam] [--local-variable-prob LOCAL_VARIABLE_PROB] [--error-filter-patterns ERROR_FILTER_PATTERNS]

optional arguments:
  -h, --help            show this help message and exit
  -g {base,api}, --generator {base,api}
                        Type of generator
  --api-doc-path API_DOC_PATH
                        Path to API docs
  -s SECONDS, --seconds SECONDS
                        Timeout in seconds
  -i ITERATIONS, --iterations ITERATIONS
                        Iterations to run (default: 3)
  --api-rules API_RULES
                        File that contains the rules specifying the APIs used for program enumeration (used only with API-based program generation)
  --library-path LIBRARY_PATH
                        Path where the compiled library resides. (Used only with API-based program generation)
  --max-conditional-depth MAX_CONDITIONAL_DEPTH
                        Maximum depth of conditionals
  --erase-types         Erases types from the program while preserving its semantics
  --inject-type-error   Injects a type error in the generated program
  --disable-expression-cache
                        Stop caching expressions that yield certain types
  --path-search-strategy {shortest,ksimple}
                        Stategy for enumerating paths between two nodes
  -t TRANSFORMATIONS, --transformations TRANSFORMATIONS
                        Number of transformations in each round
  --batch BATCH         Number of programs to generate before invoking the compiler
  -b BUGS, --bugs BUGS  Set bug directory (default: bugs)
  -n NAME, --name NAME  Set name of this testing instance (default: random string)
  -T [{TypeErasure} [{TypeErasure} ...]], --transformation-types [{TypeErasure} [{TypeErasure} ...]]
                        Select specific transformations to perform
  --transformation-schedule TRANSFORMATION_SCHEDULE
                        A file containing the schedule of transformations
  -R REPLAY, --replay REPLAY
                        Give a program to use instead of a randomly generated (pickled)
  -e, --examine         Open ipdb for a program (can be used only with --replay option)
  -k, --keep-all        Save all programs
  -S, --print-stacktrace
                        When an error occurs print stack trace
  -w WORKERS, --workers WORKERS
                        Number of workers for processing test programs
  -d, --debug
  -r, --rerun           Run only the last transformation. If failed, start from the last and go back until the transformation introduces the error
  -F LOG_FILE, --log-file LOG_FILE
                        Set log file (default: logs)
  -L, --log             Keep logs for each transformation (bugs/session/logs)
  -N, --dry-run         Do not compile the programs
  --language {kotlin,groovy,java,scala}
                        Select specific language
  --max-type-params MAX_TYPE_PARAMS
                        Maximum number of type parameters to generate
  --max-depth MAX_DEPTH
                        Generate programs up to the given depth
  -P, --only-correctness-preserving-transformations
                        Use only correctness-preserving transformations
  --timeout TIMEOUT     Timeout for transformations (in seconds)
  --cast-numbers        Cast numeric constants to their actual type (this option is used to avoid re-occrrence of a specific Groovy bug)
  --disable-function-references
                        Disable function references
  --disable-use-site-variance
                        Disable use-site variance
  --disable-contravariance-use-site
                        Disable contravariance in use-site variance
  --disable-bounded-type-parameters
                        Disable bounded type parameters
  --disable-parameterized-functions
                        Disable parameterized functions
  --disable-sam         Disable SAM coercions
  --local-variable-prob LOCAL_VARIABLE_PROB
                        Probability of assigning an expression to a local variable
  --error-filter-patterns ERROR_FILTER_PATTERNS
                        A file containing regular expressions for filtering compiler error messages
```

## Example: Testing the Java compiler

We provide an example that demonstrates the `thalia` testing framework.
The input of `thalia` is an API encoded as a set of JSON files
that contain all classes and their enclosing
methods and  fields.
Example APIs can be found at `example-apis/`.
In this example,
we leverage the API of the Java's standard library
(see `--api-doc-path example-apis/java-stdlib/json-docs`)
to stress-test `javac`.
Specifically, we produce 30 test programs in batches of 10.
The results of our testing procedure are found in
the `bugs/java-session/` directory
specified by the `--name java-session` option.

```
 thalia --language java --transformations 0  \
     --batch 10 -i 30 -P \
	 --max-depth 2 \
	 --generator api \
	 --api-doc-path example-apis/java-stdlib/json-docs \
	 --api-rules example-apis/java-stdlib/api-rules.json \
	 --keep-all \
	 --name java-session

```

The expected outcome is:

```
stop_cond             iterations (30)
transformations       0
transformation_types  TypeErasure
bugs                  /home/thalia/bugs
name                  java-session
language              java
compiler              javac 11.0.12
=============================================================================================
Test Programs Passed 30 / 30 ✔          Test Programs Failed 0 / 30 ✘
Total faults: 0
```

Among other things,
the `bugs/java-session/` directory contains two files:
`stats.json` and `faults.json`.

`stats.json` contains the following details about the testing session.

```json
{
  "Info": {
    "stop_cond": "iterations",
    "stop_cond_value": 30,
    "transformations": 0,
    "transformation_types": "TypeErasure",
    "bugs": "/home/thalia/bugs",
    "name": "java-session",
    "language": "java",
    "generator": "api",
    "library_path": null,
    "erase_types": false,
    "inject_type_error": false,
    "compiler": "javac 11.0.12"
  },
  "totals": {
    "passed": 30,
    "failed": 0
  },
  "synthesis_time": 6.266110500000002,
  "compilation_time": 0.9707086086273193
}
```

In this example, `faults.json` is empty. If there were some bugs detected,
`faults.json` would look like the following JSON file.

```json
{
  "10": {
    "transformations": [],
    "error": "5: error: incompatible types: boolean cannot be converted to Q",
    "programs": {
      "/tmp/tmp9udxjfh7/src/daiquiri/Main.java": true
    },
    "time": 0.01982936600000018
  }
}

```

This an example of an unexpected compile-time error.
When finding a bug, `thalia` stores the bug-revealing test case inside
the directory of the current testing session (e.g., `bugs/java-session`).

```
|-- 10
|   |-- Main.java
|   `-- Main.java.bin
|-- logs
|   `-- api-generator
|-- generator
|-- faults.json
`-- stats.json
```


Note that the option `--keep-all` allows you to store all the synthesized programs
into disk. They can be found in the `bugs/java-session/generator/` directory.

###  Logging

The `-L` option allows you to log all the typing sequences
synthesized by `thalia`.
The resulting logs can be found
at the `bugs/java-session/logs/api-generator` file.
In our previous example,
the contents of this file look like:

```
Built API with the following statistics:
	Number of nodes:13225
	Number of edges:19736
	Number of methods:9658
	Number of polymorphic methods:425
	Number of fields:1068
	Number of constructors:1159
	Number of types:1095
	Number of type constructors:144
	Avg inheritance chain size:4.20
	Avg API signature size:2.43

Generated program 1
	API: java.lang.module.ModuleDescriptor.Builder.version(Classifier[java.lang.module.ModuleDescriptor.Version])
	Type variable assignments:
	receiver: java.lang.module.ModuleDescriptor.Builder
	parameters java.lang.module.ModuleDescriptor.Version
	return: java.lang.module.ModuleDescriptor.Builder
Correctness: True
Generated program 2
	API: java.lang.module.ModuleDescriptor.Builder.version(Classifier[java.lang.module.ModuleDescriptor.Version])
	Type variable assignments:
	receiver: java.lang.module.ModuleDescriptor.Builder
	parameters java.lang.module.ModuleDescriptor.Version
	return: Object
Correctness: True
...
```

The first lines of the `bugs/java-session/logs/api-generator` file dumps
some statistics regarding the input API and the corresponding
API graph (e.g., number of methods, number of constructors, etc.).
Then,
the file shows the typing sequence which every test case comes from.
For example,
the first test program invokes the
[java.lang.module.ModuleDescriptor.Builder.version](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/module/ModuleDescriptor.Builder.html#version(java.lang.module.ModuleDescriptor.Version))
method found in the standard library of Java
using a parameter of type
[java.lang.module.ModuleDescriptor.Version](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/module/ModuleDescriptor.Version.html).
The result of this method call is assigned to a variable of type
[java.lang.module.ModuleDescriptor.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/module/ModuleDescriptor.Builder.html).


# Supported Languages

Currently, `thalia` generates programs written in
four popular programming languages, namely,
Java, Scala, Kotlin, and Groovy. Use the
option `--language` to specify the target language.

To support a new language,
you need to implement the following:

* A translator that converts a program written in the
IR into a program written in the target language.
To to so, you have to extend the
[src.translators.base.BaseTranslator](https://github.com/hephaestus-compiler-project/hephaestus/blob/main/src/translators/base.py)
class.

* A class that reads compiler messages and distinguishes
compiler crashes from compiler diagnostic error messages.
To do so, you must extend the 
[src.compilers.base.BaseCompiler](https://github.com/hephaestus-compiler-project/hephaestus/blob/main/src/compilers/base.py)
class.

* (Optionally) Any built-in types supported by the language, e.g., see
[Java types](https://github.com/hephaestus-compiler-project/hephaestus/blob/main/src/ir/java_types.py) for guidance.


# Related publications

* Stefanos Chaliasos, Thodoris Sotiropoulos, Diomidis Spinellis, Arthur Gervais, Benjamin Livshits, and Dimitris Mitropoulos. [Finding Typing Compiler Bugs](https://doi.org/10.1145/3519939.3523427). In Proceedings of the 43rd ACM SIGPLAN Conference on Programming Language Design and Implementation, PLDI '22. ACM, June 2022.
* Stefanos Chaliasos, Thodoris Sotiropoulos, Georgios-Petros Drosos, Charalambos Mitropoulos, Dimitris Mitropoulos, and Diomidis Spinellis. [Well-typed programs can go wrong: A study of typing-related bugs in JVM compilers](https://doi.org/10.1145/3485500). In Proceedings of the ACM on Programming Languages, OOPSLA '21. ACM, October 2021.

# Related Artifacts

* [Replication Package for Article: Finding Typing Compiler Bugs](https://zenodo.org/record/6410434) March 2022 software.
* [Replication Package for Article: "Well-Typed Programs Can Go Wrong: A Study of Typing-Related Bugs in JVM Compilers"](https://doi.org/10.5281/zenodo.5411667) October 2021 software.
