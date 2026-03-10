# Night Crows Codex Skill

Shareable Codex repo for the `night-crows-translate-th` skill.

## Included Skill

- `night-crows-translate-th`

The shared copy includes the full skill folder:

- `SKILL.md`
- `agents/openai.yaml`
- `scripts/`
- `assets/NCGlosarry01.json`

## Install

```bash
git clone https://github.com/nuttyjibaso-svg/night-crows-translate-th-share.git
cd night-crows-translate-th-share
python3 install.py
```

The installer copies everything under `skills/` into `$CODEX_HOME/skills` or `~/.codex/skills`.

After install, restart Codex.

## Use

Example prompt:

```text
Use $night-crows-translate-th to translate this Night Crows announcement from English to Thai while enforcing the glossary and preserving formatting.
```

Batch file example:

```text
Use $night-crows-translate-th to prepare and translate this Night Crows CSV file to Thai.
```

## Batch Scripts

The skill bundle includes local helpers for:

- glossary lookup
- translation output validation
- batch `.txt` and `.csv` preparation and merge

Those scripts are already inside `skills/night-crows-translate-th/scripts/`.

## Manual Install

If needed, copy `skills/night-crows-translate-th/` into `$CODEX_HOME/skills/`, then restart Codex.

