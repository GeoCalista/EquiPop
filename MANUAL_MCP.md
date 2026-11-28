# EquiPop from an AI assistant — The MCP Manual

*A gentle guide for people who have used an AI assistant and want it
to run EquiPop on their own files. No Python needed for the Claude
Desktop route. For what the tools compute, see the Beginner's Manual;
for the short technical reference, README_MCP.md.*

---

## 0. The idea, in one paragraph

You already describe your research problem to an assistant such as
Claude or ChatGPT. Until now the assistant could only talk about
EquiPop; with this, it can **use** it. A small program, the EquiPop
server, runs on your own computer. The assistant asks it questions
("which tools are there?", "what is in this file?") and gives it work
("run tool 1 on this file with k = 500"). The server does the work on
your computer with the same engine QGIS, ArcGIS Pro and Stata use,
writes the result to a new file next to your data, and tells the
assistant what came out, in summaries. You read the assistant's
account, open the file in your GIS, and go on.

## 1. What the assistant can and cannot do

**It can:**

- list EquiPop's tools and explain each one, in the words of the QGIS
  and Pro dialogs;
- tell you how to cite EquiPop and the method paper behind the tool
  you used, correctly, from the project's own citation file;
- look at a file or a folder of yours and tell you what is in it:
  layers, columns, how many rows, the coordinate system, the extent;
- run **tool 1, Counts and Shares** (the k nearest people, counts and
  shares of a group), **tool 2, Value Statistics** (mean, median, Gini
  and more of a value among the k nearest), **tool 1b, Summaries by
  area** (the same per ward or municipality), and **tool 3b, Green
  reach** (from a land-cover map, with rasterio installed), on files
  you name;
- explain what a result column means, such as `R_foreign_500`.

**It cannot:**

- see your rows. It gets descriptions and summaries, never the data
  (section 5);
- run the other tools (rasters at continental scale, demography,
  fetching data, who goes where). Those run in QGIS, Pro or Python;
- change or delete anything. Every result is a new file;
- make a map. Open the result file in QGIS or Pro for that;
- replace your judgement. It can misread your question or your
  result, just as it can with anything else.

## 2. Installing in Claude Desktop (one click)

Claude Desktop is the Claude app for Windows and Mac (not the web
page). The EquiPop server comes as one file, `equipop-<version>.mcpb`,
and the app installs it the way a phone installs an app.

1. Go to EquiPop's release page on GitHub, open the latest release,
   and download `equipop-<version>.mcpb`.
2. Double-click the file. Claude Desktop opens, shows what the server
   is and asks you to install it. Say yes.
3. The first start takes a minute or two: the app fetches its own
   Python and EquiPop's dependencies into a private folder of its own.
   Nothing is added to your Python, conda, QGIS or Pro. You need the
   internet for this first start, not afterwards.
4. Start a new chat and ask: *Which EquiPop tools are there?* If the
   assistant answers with the list, you are done.

**Updating:** download the new `.mcpb` and open it; the app replaces
the old one. **Removing:** Settings → Extensions (or Connectors) →
EquiPop → remove. Your result files stay where they were written.

## 3. Installing for another assistant, or from your own Python

If you use ChatGPT, Copilot, VS Code or another assistant that speaks
MCP, or want the server to run in a Python you already have, see
README_MCP.md: it is `pip install "equipop[mcp]"` and a few lines in
the assistant's settings file that say "start `equipop mcp`". The
server is the same whichever way it starts.

## 4. The first conversation

Say what you have and what you want, as you would to a colleague. The
assistant works out which tools to call. A typical first session:

> **You:** Look at C:\data\people2024.gpkg and tell me what is in it.
>
> **Assistant:** *(calls equipop_look)* One layer, 1,204,331 points in
> SWEREF99 TM (EPSG:3006), columns id, pop, age, income, foreign …
> pop has a mean of 3.2 people per point …
>
> **You:** Run tool 1 with k = 100, 500 and 2000, people in pop,
> counting foreign.
>
> **Assistant:** *(calls equipop_counts_and_shares)* Done. The result
> is in C:\data\people2024_counts.gpkg with nine new columns:
> Dist_100 … R_foreign_2000. The median Dist_500 is 410 m; the share
> R_foreign_500 has a mean of 0.19 and a 90th percentile of 0.47 …
>
> **You:** What does Dist_500 mean exactly?
>
> **Assistant:** *(calls equipop_columns)* The distance from the point
> to the edge of the neighbourhood that holds its 500 nearest people …
>
> **You:** How do I cite this?
>
> **Assistant:** *(calls equipop_cite)* For every use, Östh (2014),
> the software report … for tool 1 also Östh, Clark and Malmberg
> (2015), Geographical Analysis …

Then open `people2024_counts.gpkg` in QGIS and look at the map.

## 5. What leaves your computer — read this

The server runs on your computer, but **whatever a tool returns is
sent to the assistant, and so to the servers of the company that runs
it**. With register data, that is the thing to think about. EquiPop's
rule (R-63) is:

- a tool returns **descriptions and summaries only**: column names,
  how many rows, the extent, the coordinate system, and for each
  numeric column how many are missing, how many distinct values, the
  mean, the median and the 10th and 90th percentiles. Not the minimum
  or the maximum, because those are one person's values;
- the full result is written to a **new file next to your input**;
  the assistant is told the path and the summaries, not the rows;
- **no row ever leaves** unless you yourself start the server with the
  switch `--rows`, and then only the first twenty of a file, on
  request. The one-click install does not have that switch;
- nothing is overwritten or deleted. A second run writes
  `name_counts_2.gpkg` beside `name_counts.gpkg`;
- the server opens only the file or folder you name.

Two things this does not cover. First, **what you type** goes to the
assistant too: do not paste rows into the chat. Second, **a mean is
still a statistic about your data**; if your data may not leave the
building even as an aggregate — a secure research environment, a
statistics office's protocol — this route is not for that data unless
the assistant itself runs inside the same walls (see section 8).

## 6. Good questions, and how to put them

The assistant reads the same help you would. Help it by naming:

- **the file**, with its full path (`C:\data\people.gpkg`, or on a
  Mac `/Users/you/data/people.gpkg`). Ask it to *look* first;
- **k or a radius** — "k = 100, 500 and 2000", "radius 1000 m";
- **the people field**, when a point is more than one person
  (a grid cell, a building). Without it every point counts as one,
  and the assistant should warn you if a `pop`-like column is there;
- **what to count or summarise** — "count foreign", "mean and Gini of
  income";
- **for tool 1b**, the areas file and, when wards and municipalities
  are in one layer, the level field.

Questions that work well:

- *Which of EquiPop's tools fits "how segregated is the city at
  different scales"?* — the assistant reads the tools' summaries and
  usage notes and suggests one;
- *Before running, tell me what tool 2 will write.* — it reads the
  help and lists the columns;
- *Summarise the result's R_foreign_500 by the municipalities in
  kommuner.gpkg.* — tool 1b on tool 1's output: neighbourhoods drawn
  by people beside areas drawn by borders;
- *Why are 300 points reported as snapped?* — it reads the run's
  messages, which the server returns with every result.

## 7. When something goes wrong

- **"Points are in DEGREES"**: the file holds longitude and latitude.
  Ask the assistant to run again "with project = true"; the run then
  places the points in UTM metres and says which zone it used. Better
  still, save the file in metres in your GIS.
- **"No coordinate pair was recognised"**: a table with unusual column
  names. Tell the assistant which columns are x and y.
- **"The areas are in EPSG:4326 and the points in EPSG:3006"**: save
  one of the layers in the other's system in your GIS. (The QGIS and
  Pro versions of tool 1b do this for you.)
- **"Tool 3b needs rasterio"**: the one-click install does not include
  rasterio. Install the Python route (section 3) with
  `pip install "equipop[mcp]" rasterio`, or run tool 3b in QGIS or Pro.
- **The assistant says it cannot find the server**: restart the app;
  on first install, give the first start its minute. In Claude
  Desktop, Settings → Extensions shows whether EquiPop is enabled and
  its log.
- **A number looks wrong**: run the same thing in QGIS or Pro; the
  numbers must agree to the last decimal, because it is the same
  engine. If they do not, that is a bug: send both runs' messages.

## 8. Behind walls

In a secure research environment the assistant you talk to cannot
reach your computer, and that is the point of the wall. The server
itself needs no network and installs from a wheel carried in; what it
needs is an assistant inside the wall, such as a local model with an
MCP client. Whether that, and which summaries may cross the wall, is
for the environment's own protocol, not for EquiPop, to decide. Ask
before connecting anything.

## 9. For the technically minded

The server is `equipop mcp`, a command installed with the Python
package. `equipop doctor` says what is installed, `equipop help 1b`
prints a tool's help, `equipop cite 2` the citation. The tools' names
start with `equipop_`; their descriptions, which are what the
assistant reads, are in `equipop/mcp/server.py`; the reading and
writing rules in `equipop/mcp/files.py`. The server is listed in the
MCP Registry as `io.github.geocalista/equipop`.
