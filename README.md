# analyst-toolkit

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

## Roadmap

See [BACKLOG.md](BACKLOG.md).

## Licence

MIT, per project. See [LICENSE](LICENSE).
