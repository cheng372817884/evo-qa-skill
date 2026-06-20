# Imported Knowledge Sources

## 1. Bach/Bolton Heuristics (MCOASTER + 11 mnemonics)
- **Repo**: github.com/danashby/Exploratory-Testing-Skill
- **License**: MIT
- **Form**: Claude Code skill
- **Contains**:
  - FEW HICCUPPS — test oracles
  - SFDIPOT — product coverage (San Francisco Depot)
  - MCOASTER — session report structure
  - I SLICED UP FUN — mobile testing
  - FCC CUTS VIDS — application touring
  - RCRCRC — regression prioritisation
  - FAILURE — error handling
  - RIMGEA — bug advocacy
  - CRUSSPIC STMPL — non-functional attributes
  - FIBLOTS / IVECTRAS — performance
  - Goldilocks / ZOM / CRUD / BME — data heuristics
  - SBTM — session-based test management
- **How we use it**: integrate into our universal `knowledge/heuristics/` layer
  Each mnemonic becomes a separate file with frontmatter for retrieval.

## 2. ISTQB CTFL v4.0 Vocabulary
- **Repo**: github.com/bloomikko/ISTQB-CTFL-V4.0
- **License**: (per repo)
- **Form**: 346-line glossary
- **Contains**: ~80 industry-standard QA terms with definitions
- **How we use it**: import into `knowledge/glossary/istqb.md` as canonical terminology
  Used by Glossary lookup component (the "issue policy" → prerequisite chain example)

## 3. Faker (PyPI)
- **Repo**: github.com/joke2k/faker (19k⭐)
- **License**: MIT
- **How we use it**: depend on it for unique test data generation
  Fixture system uses Faker for emails/names/phones/addresses

## 4. factory_boy + pytest-factoryboy
- **Repos**: github.com/FactoryBoy/factory_boy (3.8k⭐) / pytest-dev/pytest-factoryboy (400⭐)
- **License**: MIT
- **How we use it**: optional — for projects that want code-defined fixtures
  Our default fixtures are YAML-based, factory_boy is escape hatch
