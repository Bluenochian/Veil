# Bundled domain classification data

Veil includes an offline SQLite domain index at `veil/data/adult_domains.db`. It is built from The Block List Project's **Porn Block List** (953,393 unique domains) and distributed with the application so classification works without separate setup or a network connection.

- **Source:** [The Block List Project](https://github.com/blocklistproject/Lists), `porn.txt`
- **Pinned source revision:** [`ee3bdbaddf49c756cf3340bb2e6a9dee5282d1c6`](https://github.com/blocklistproject/Lists/tree/ee3bdbaddf49c756cf3340bb2e6a9dee5282d1c6) (release `v2026.10.26`)
- **Source list license:** MIT (declared in the `porn.txt` header)
- **Repository license:** [Unlicense](https://github.com/blocklistproject/Lists/blob/main/LICENSE)
- **Attribution:** The Block List Project and its contributors
- **Build:** `python3 scripts/build_domain_index.py` generates the indexed database from the pinned upstream list; the builder verifies its record count and SQLite integrity.

**License separation:** Veil's original application source and artwork remain under [PolyForm Noncommercial 1.0.0](LICENSE). The upstream domain dataset retains its own permissive licensing and is not relicensed as PolyForm. See [third-party notices](THIRD_PARTY_NOTICES.md).

The index is processed locally. Classification also considers URL/title heuristics, local allowlist/blocklist overrides, and context. No static list guarantees complete coverage or eliminates false positives.

## MIT permission notice for the bundled dataset

The source file identifies the list as MIT-licensed. The dataset attribution is **The Block List Project and contributors**. The MIT permission notice is reproduced here to accompany redistributed copies:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
