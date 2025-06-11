# Contributing to **App Use** 🚀

Thank you for your interest in improving App Use! 🎉
Your contributions help us build the easiest way to connect AI agents with mobile apps.
This guide will walk you through everything you need to know to get started.

---

## Development Quick Setup

```bash
# 1. Fork & clone
git clone https://github.com/<your-github-handle>/app_use.git
cd app_use

# 2. Install Python deps (≥3.11) with all extras + dev tools
uv sync --all-extras --dev          # if you use uv (recommended)

# 3. Install & start Appium (needed for tests that hit real/sim devices)
npm install -g appium appium-doctor
appium   # runs on :4723 by default
```

For a deeper dive into device & driver setup, see `docs/env-setup.md`.

---

## How to Contribute

### 1. Find Something to Work On

- **Feature ideas** → browse open issues labeled `enhancement` or ask for suggestions in **[Discord](https://discord.gg/V9mW8UJ6tx)**.
- **Show & tell** → share cool projects or prompt libraries in `#showcase-your-work`.

### 2. Make a Great Pull Request ✨

1. **Describe the change** – what does it do and *why* is it needed?
2. **Keep it focused** – tackle one issue/feature per PR.
3. **Add tests** – green CI ➜ happy maintainers.
4. **Show it off** – a screenshot, GIF, or example script helps reviewers see the impact.

---

## Contribution Process

1. **Fork** the repo and create your branch: `git checkout -b feat/awesome-thing`.
2. **Hack** – make your changes locally.
3. **Test** – run your changes and test them (we will be adding tests really soon)
4. **Commit** – follow conventional commits (e.g., `feat: add calendar helper`).
5. **Push & PR** – open your pull request against `main`.
6. **Discuss** – respond to any review feedback.
7. **Merge & celebrate** 🎊

Need faster feedback? Feel free to ping the thread or say hi in [Discord](https://discord.gg/V9mW8UJ6tx).

---

## Code of Conduct 🤝

We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) to ensure a welcoming, inclusive community. Please treat everyone with respect.

---

## Getting Help

- **[Discord](https://discord.gg/V9mW8UJ6tx)** – chat with maintainers & the community.
- **GitHub Discussions / Issues** – ask technical questions.
- **Docs** – check the README and `docs/` directory.

We can't wait to see what you build! 💜
