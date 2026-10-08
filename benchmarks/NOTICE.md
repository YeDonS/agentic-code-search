# Data provenance and attribution

Historical reports, labels, and solution relationships come from
[SWE-bench Lite](https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite), revision
`b0dde1093fe417d83b7184254edf8199c1f0dff5`, associated with
[SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770).
This repository's MIT license covers its original implementation, not a relicensing of
upstream issue text, patches, or source code.

Each task links its maintainer solution PR. Reference records contain paths, test IDs, and
hashes; full gold patches and downloaded source archives stay in the ignored local cache.
Curated prediction records omit historical source excerpts. Upstream rights and licenses
remain with their respective authors:

| Upstream repository | Selected tasks |
|---|---:|
| [astropy/astropy](https://github.com/astropy/astropy) | 6 |
| [django/django](https://github.com/django/django) | 12 |
| [matplotlib/matplotlib](https://github.com/matplotlib/matplotlib) | 12 |
| [mwaskom/seaborn](https://github.com/mwaskom/seaborn) | 4 |
| [pallets/flask](https://github.com/pallets/flask) | 3 |
| [psf/requests](https://github.com/psf/requests) | 6 |
| [pydata/xarray](https://github.com/pydata/xarray) | 5 |
| [pylint-dev/pylint](https://github.com/pylint-dev/pylint) | 6 |
| [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | 12 |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | 12 |
| [sphinx-doc/sphinx](https://github.com/sphinx-doc/sphinx) | 11 |
| [sympy/sympy](https://github.com/sympy/sympy) | 11 |

No endorsement by upstream maintainers is implied. This is an independently selected
local benchmark, not a SWE-bench leaderboard result.
