# Where is KGroot Services?

If you just pulled the branch and can't find `kgroot-services`, here's where it is:

## Directory Structure

```
kgroot-latest/                    ← Root of repository
└── mini-server-prod/             ← Go here first
    └── kgroot-services/          ← KGroot RCA system is here!
        ├── README.md
        ├── QUICKSTART.md
        ├── run_demo.sh
        ├── example_usage.py
        └── ...
```

## Navigation Commands

```bash
# From repository root (kgroot-latest/)
cd mini-server-prod/kgroot-services

# Or in one command from anywhere in the repo
cd $(git rev-parse --show-toplevel)/mini-server-prod/kgroot-services

# Verify you're in the right place
ls -la
# Should show: README.md, QUICKSTART.md, run_demo.sh, example_usage.py, etc.
```

## Quick Start From Your Location

```bash
# If you just did: git checkout feature/kgroot-implementation
# You're probably in: ~/kgroot-latest/

# Do this:
cd mini-server-prod/kgroot-services
./run_demo.sh
```

## Full Path Examples

On Ubuntu server:
```bash
~/kgroot-latest/mini-server-prod/kgroot-services/
```

On Mac:
```bash
/Users/yourname/kgroot_latest/mini-server-prod/kgroot-services/
```

## Verify Installation

```bash
cd mini-server-prod/kgroot-services

# You should see these files:
ls
# Output should include:
# README.md
# QUICKSTART.md
# run_demo.sh
# example_usage.py
# requirements.txt
# config.yaml.example
# core/
# models/
# graphrag/
# utils/
```

## Common Mistake

❌ **Wrong**: Being in `kgroot-latest/` and trying to run scripts
```bash
~/kgroot-latest$ ./run_demo.sh
# Error: file not found
```

✅ **Correct**: Navigate to the right subdirectory first
```bash
~/kgroot-latest$ cd mini-server-prod/kgroot-services
~/kgroot-latest/mini-server-prod/kgroot-services$ ./run_demo.sh
# Success!
```

---

**TL;DR**:
```bash
cd mini-server-prod/kgroot-services
```
