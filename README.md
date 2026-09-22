# analyst-toolkit

[![tests](https://github.com/Keremozdemirra/analyst-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/Keremozdemirra/analyst-toolkit/actions/workflows/tests.yml)

Strategy and finance work runs on spreadsheets that get copied, edited and
re-copied until nobody can say where a number came from. The analysis itself is
usually sound; the medium is what fails.

This repository implements the recurring analytical steps of that work as
tested code with a readable audit trail: sizing a market, valuing a business,
running scenarios, comparing a peer set, and turning a messy export into
something you can actually compute on.

It is not a modelling framework and does not want to be one. Each tool does one
job and can be read in a sitting.

Each tool lives in its own folder with its own README and its own tests, and
leans on the Python standard library unless a dependency genuinely earns its
place.

## Layout

```
projects/
  NNN-project-name/
    README.md          what it does, how to run it, what it is not
    <package>/         the implementation
    tests/             python3 -m unittest discover -s tests -t .
    examples/          a working input file
    pyproject.toml     dependencies, if any
```

## Projects

| # | Project | What it does |
| --- | --- | --- |
| 001 | [market-sizer](projects/001-market-sizer) | Sizes a market top-down and bottom-up side by side, then inverts the model to report what each assumption would have to be for the two to agree — and which ones cannot close the gap at all. |
| 002 | [dcf-lab](projects/002-dcf-lab) | Values a business from named drivers with the cost of capital built up rather than asserted, values the terminal period both ways so each checks the other, and splits the answer into the part that was forecast and the part that was not — which is usually most of it. |

## Roadmap

See [BACKLOG.md](BACKLOG.md).

## Runs in the browser

Each project here is also a case study on the author's site, with the method, the assumptions and what it refuses to answer, and a version that runs in the page:

- [Discounted cash flow](https://keremozdemir.de/cases/dcf-lab/)
- [Market sizer](https://keremozdemir.de/cases/market-sizer/)

## Licence

MIT, per project. See [LICENSE](LICENSE).
