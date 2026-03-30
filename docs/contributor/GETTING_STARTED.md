# Contributing to GraalPy: Getting started
Thanks for considering contributing to GraalPy. This guide aims at helping you through your first contribution to the project. 
For additionnal support, please feel free to join our [community slack](www.graalvm.org/slack-invitation/).

Find below a summary of the contribution workflow:
- [Open or select an issue](#1-file-an-issue)
- [Setup your environment](#2-setup-your-environment)
- [Run tests](#3-run-tests)
- [Run Pull Request CI](#4-pull-request)

## 1. File an issue
Ensure there is an issue created to track and discuss the fix or enhancement you intend to submit.
Issues labeled with "[good first issue](https://github.com/oracle/graalpython/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)" are recommended to get started.

If no issue references your problem, please file one using either the Bug Report or the Feature Request [issue Form](https://github.com/oracle/graalpython/issues/new/choose).
![Issue Form](/docs/contributor/assets/issue_form_selector.png)

If you think you've found a security vulnerability, do not raise a GitHub issue and follow the instructions in our [security policy](https://github.com/Ariouz/graalpython/blob/master/SECURITY.md).


## 2. Setup your environment

### Using Codespace:
See [Using a Github codespace](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md#using-a-github-codespace) to open the project in a GitHub Codespace.

If you have a GitHub Copilot Pro subscription, using Codespace is a convenient way to run AI agents in an isolated environment without extra setup.

### Locally:

As you will need to use `mx`, it is highly recommended to first read [Contributing to GraalPy](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md#setting-up-on-your-machine) to set up your environment.

- Fork and clone the repository
- Create a new branch from master using
```bash
git checkout master
git checkout -b <branch-name>
```
- Init your IDE settings using
```bash
mx ideinit
```

## 3. Run tests

To test your changes, run `mx build` - you should always run `mx clean` before building again. GraalPy will be built under `mxbuild/`.

You can find a list of useful mx commands below:
- `mx clean`: Clean build files
- `mx build`: Build graalpy
- `mx python-svm`: Build graalpy native
- `mx gate --tags python-unittest`: Run python unittests
- `mx gate --tags python-junit`: Run JUnit python unittests
- `mx graalpytest <path-to-file>::<test-name>`: Run specific python test
    <details>
    <summary>Example using mx graalpytest</summary>

    ```bash
    mx graalpytest graalpython/lib-python/3/test/test_threading.py::test.test_threading.ExceptHookTests.test_excepthook
    ```
    </details>

- `mx ideinit`: Init IDE settings (VS Code, IntelliJ Idea, Eclipse)
For full command list, use `mx help`.

## 4. Pull Request
For any PR to be merged, you need to sign the [Oracle Contributor Agreement (OCA)](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md#contributing-to-graalpy).

Once your Pull Request is marked as `Ready for review`, the [CI](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md#ci-unittests) will run all tests gates.
You can open a PR in your own fork to run the CI anytime you want.

Note that the CI doesn't run on draft PRs.
