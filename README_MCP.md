# EquiPop from an AI assistant - the MCP server

EquiPop's fourth door, beside QGIS, ArcGIS Pro and Stata. An AI
assistant that speaks MCP (Claude, ChatGPT, Copilot, VS Code and
others) connects to a small server running on your own computer, and
can then:

- list EquiPop's tools and read each one's help, in the words of the
  QGIS and Pro dialogs;
- cite EquiPop correctly - the software report, the version, and the
  method paper behind the tool you used (these come from CITATION.cff;
  the assistant does not invent them);
- look at a file or folder of yours without seeing its rows;
- run **tool 1** (counts and shares), **tool 1b** (summaries by area),
  **tool 2** (value statistics) and, with rasterio installed, **tool
  3b** (green reach) on a file you name, with the same boxes as the
  dialogs;
- explain what a result column means.

The other tools (rasters, demography, fetching, who goes where) run in
QGIS, Pro or Python today, not through the server yet.

## What leaves your computer - ruling R-63

The server runs on your computer, but **everything a tool returns goes
to the assistant, and so to the AI company's servers**. With register
microdata that is the leak to close. So:

- a tool returns **descriptions and summaries only**: column names, how
  many rows, the extent, the coordinate system, and per column how
  many are missing, how many distinct values, the mean, the median and
  the 10th and 90th percentiles. Not the minimum or the maximum, which
  are one person's values;
- the full result is written to a **new file next to the input**, and
  the assistant receives the file's path;
- **no row leaves** unless you start the server yourself with
  `--rows`, and then only through `equipop_peek`, at most twenty;
- nothing is overwritten or deleted. A second run writes
  `name_counts_2.csv` beside `name_counts.csv`;
- the server opens the file or folder it is given and nothing beside
  it.

If your data may not leave your computer at all, not even as a mean,
do not connect it to an assistant hosted elsewhere.

## Install

### Claude Desktop, one click

1. On the release page, download `equipop-<version>.mcpb`.
2. Open it (double-click). Claude Desktop shows what it is and
   installs it. The first start takes a minute: the app fetches its
   own Python and EquiPop's dependencies into a private environment.
   Nothing is added to your Python, conda or QGIS.
3. In a new chat, ask: *"Which EquiPop tools are there?"*

### Any assistant, from the Python package

With a Python you can type in (Anaconda Prompt, a terminal):

```
pip install "equipop[mcp]"
equipop mcp
```

`equipop mcp` starts the server on standard input and output and waits
for an assistant; it prints nothing. Tell the assistant where it is.
For Claude Desktop that is `claude_desktop_config.json`, for others
their own settings file; the entry is the same:

```json
{
  "mcpServers": {
    "equipop": {
      "command": "equipop",
      "args": ["mcp"]
    }
  }
}
```

If `equipop` is not on the assistant's PATH, give the full path of the
Python that has it, with `-m equipop mcp`:

```json
{
  "mcpServers": {
    "equipop": {
      "command": "C:\\Users\\you\\.conda\\envs\\equipop\\python.exe",
      "args": ["-m", "equipop", "mcp"]
    }
  }
}
```

With [uv](https://docs.astral.sh/uv/) installed, no install at all:

```json
{
  "mcpServers": {
    "equipop": {
      "command": "uvx",
      "args": ["--python", ">=3.11", "--from", "equipop[mcp]", "equipop", "mcp"]
    }
  }
}
```

To let rows leave (R-63), add `"--rows"` to `args`.

### The registry

The server is listed in the official MCP Registry as
`io.github.geocalista/equipop`, so an assistant that searches the
registry finds it by the problems it solves: individualised
neighbourhoods, k nearest neighbours, segregation at many scales,
accessibility, summaries by area.

## What to ask

- *"Look at C:\data\people.gpkg and tell me what is in it."*
- *"Run tool 1 on it with k = 100, 500 and 2000, people in the field
  `pop`, counting `foreign`."*
- *"Summarise the result's R_foreign_500 by the municipalities in
  C:\data\kommuner.gpkg."*
- *"What does Dist_500 mean?"*
- *"How do I cite this?"*

The assistant calls `equipop_look`, `equipop_counts_and_shares`,
`equipop_summaries_by_area`, `equipop_columns` and `equipop_cite`, and
tells you the path of each file it wrote.

## The tools

| Tool | Does |
|---|---|
| `equipop_tools` | lists the tools, their groups and what each does |
| `equipop_help` | one tool's help: summary, usage, every box |
| `equipop_cite` | how to cite, text and BibTeX, per tool or aspect |
| `equipop_columns` | what result columns mean |
| `equipop_look` | what is in a file or folder, without rows |
| `equipop_counts_and_shares` | tool 1 on a file |
| `equipop_value_statistics` | tool 2 on a file |
| `equipop_summaries_by_area` | tool 1b on a points file and an areas layer |
| `equipop_green_reach` | tool 3b on a points file and a raster (rasterio) |
| `equipop_peek` | the first rows - only with `--rows` |

Files it reads: csv, tsv, xlsx, parquet, dta, sav, dbf; gpkg, shp,
geojson, fgb (geopandas); tif, vrt, img, asc (rasterio). Points in
degrees are refused unless the call says `project: true`, which places
them in UTM metres for the run and says which zone.

## The same words everywhere

The help the assistant reads is the help the dialogs show
(`equipop/doors/help.py`), and the numbers are the engine's, the same
every door gives: a run through the server and the same run in QGIS
agree to the last decimal. `equipop help 1b` prints the same help in
a terminal; `equipop doctor` says what is installed.
