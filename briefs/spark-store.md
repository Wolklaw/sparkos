# Spark Store (with the Spark Portal inside)

Read [README.md](README.md) first for the conventions every Spark app follows (Python + Tk, house
style, `files/spark-store/`, `install.sh`, `--self-test`, tests, workflow). Add
`files/scripts/spark-store.sh` (the build step), but don't edit `recipes/recipe.yml`,
`boot-test.yml` or `files/scripts/sparkos-defaults.sh`: the main SparkOS session wires it in and
retires Bazaar when the owner says it's ready. This is Release 3 work: take the time to do it well.

## Why

SparkOS's store today is Bazaar, another project's app. The owner wants SparkOS to rely on others
as little as possible ([PLAN.md, Independence roadmap](../PLAN.md)) and planned a "Spark Portal"
listing the optional Spark apps. Spark Store is both: one store where people find the Spark apps
and every Flathub app, the way Windows users expect a store to work.

## What it does

- **Home:** "Spark apps" first (the owner's own: installed ones marked, optional ones installable;
  read their `spark-app.json`), then curated rows (Games, Chat, Music, Creative, Office), then
  search.
- **Search** as you type, across names, summaries and keywords.
- **App page:** icon, name, who makes it (developer name, verified badge when Flathub says so),
  summary, screenshots, description, size, licence, permissions in plain words (files, devices,
  network), and Install / Open / Remove. Say plainly when an app is proprietary.
- **Installed** and **Updates** pages, with "Update all".
- **Installs** with `flatpak install --user` (no password) by default, one queue in a background
  thread, progress per app, a failure shows flatpak's error and Retry. Opening a `.flatpakref`
  file or `appstream://` link lands on that app's page.
- **Data:** from the local Flathub appstream that flatpak keeps (`flatpak update --appstream`;
  the `appstream.xml.gz` under the remote's appstream folder), so search works offline and nothing
  depends on a web API. Screenshots load from their URLs only when an app page opens, cached in
  `~/.cache/spark-store/`. No accounts, no tracking.
- **Speed:** opens in under a second with thousands of apps (index the appstream once, cache it,
  rebuild only when it changes); no CPU when idle.

## Tests

Unit tests against a small fixture appstream (a few apps, with and without screenshots,
proprietary, verified), the search ranking, the install queue against a fake `flatpak`, and the
`spark-app.json` reader. UI tests under Xvfb. In the SparkOS image (CI): `--self-test` loads the
real Flathub appstream if present (it's fetched at first boot; say so if absent) and the Spark apps
list. No real installs in CI except one small Flatpak if the runner allows it.

## Done when

CI passes in Fedora and inside the SparkOS image, the build step exists, and a PR from
`spark-store` is open for the owner, saying what's left before Bazaar can be removed.
