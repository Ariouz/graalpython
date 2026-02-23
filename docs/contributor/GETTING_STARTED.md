# Contributing to GraalPy: Getting started
As you will need to use `mx`, it is highly recommended to first read [Contributing to GraalPy](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md) to set up your environment.
This document will demonstrate the different steps to contribute to the project by fixing the following error: `cannot import name '_excepthook' from '_thread'`.


## 1. File an issue
Ensure there is an issue created to track and discuss the fix or enhancement you intend to submit.
Issues labeled with "[good first issue](https://github.com/oracle/graalpython/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22)" are recommended to get started.

If no issue references your problem, please file one using the [Bug Report issue form](https://github.com/oracle/graalpython/issues/new/choose).
![Issue Form](/docs/contributor/assets/issue_form_selector.png)

If you think you've found a security vulnerability, do not raise a GitHub issue and follow the instructions in our [security policy](https://github.com/Ariouz/graalpython/blob/master/SECURITY.md).


## 2. Apply changes
### Locally:
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

### Codespace:
See [Using a Github codespace](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md)

To test your changes, run `mx clean && mx python-jvm`, graalpy will be built under mxbuild/
You can find a list of usefull mx commands below:
- `mx clean`: Run it before any build
- `mx python-jvm`: Build graalpy jvm
- `mx python-svm`: Build graalpy native
- `mx gate --tags python-unittest`: Run python unittests
- `mx gate --tags python-junit`: Run JUnit python unittests
- `mx ideinit`: Init IDE settings (VSCode, IntelliJ, Eclipse)
For full command list, use `mx help`.

## 3. Pull Request
For any PR to be merged, you need to sign the [OCA](https://github.com/oracle/graalpython/blob/master/docs/contributor/CONTRIBUTING.md#contributing-to-graalpy).
Once marked as "ready for review", CI will run all unittests.
