# Last Z farm helper

Sends gather marches on Last Z: Survival Shooter farm accounts running in BlueStacks on a Mac. It works over ADB (Android Debug Bridge) and finds buttons by template matching (comparing the screen against small cropped images). It never touches game files or logins. It only reads the screen and sends taps.

> Automation may break the game's terms of service. Use it on farm accounts only.

## What it does

Each cycle, per BlueStacks instance:

1. Checks the march queue for an idle (sleeping "zZ") squad. If there isn't one, it waits for the next cycle.
2. Search → resource tab (Lumberyard / Farmland / Mining Zone) → forces the level slider to **Lv.6** → Search.
3. Taps the tile → Gather → March.
4. Repeats until `max_marches` is reached or no squad is idle. Resources rotate in strict order (wood, food, ...).

After the marches, timed **routines** run whenever they're due:

- **donate_tech** (every 100–130 min): Alliance → Alliance Techs → the leader's thumbs-up tech (checks the Develop, Combat and Dominator tabs) → taps the **blue zent Donate** button until attempts run out. The gem Donate button is never tapped: the bot only looks on the right half of the popup, and the zent template scores 0.40 against the gem button.
- **collect_hq** (every 60–100 min): Headquarters → city → taps all EXP, gold Z coin (zent) and food bubbles → World. **Electricity is never collected**, because there's no template for it.

Every tap lands at a random point inside its button with a random hold time. Waits and check intervals are randomized too.

## Requirements

- macOS with BlueStacks, set to a fixed **1080x1920** resolution (the templates are cut at that size)
- `brew install android-platform-tools`
- Python 3 with `opencv-python-headless pyyaml numpy`

```bash
cd ~/GitHub/lastz-farm-bot
python3 -m venv .venv && source .venv/bin/activate
pip install opencv-python-headless pyyaml numpy
```

In BlueStacks: **Settings → Advanced → Android Debug Bridge** on. Then:

```bash
adb connect 127.0.0.1:5555
python3 farm_bot.py devices
```

## Commands

| Command | Purpose |
|---|---|
| `python3 farm_bot.py devices` | List ADB devices |
| `python3 farm_bot.py snap -d 127.0.0.1:5555` | Save a full screenshot (to crop new templates from) |
| `python3 farm_bot.py test -d 127.0.0.1:5555 -t <name>` | Match score for one template |
| `python3 farm_bot.py once -d 127.0.0.1:5555 -v` | One cycle with detailed logging |
| `python3 farm_bot.py run` | Run forever in the foreground |

## Running as a background service

```bash
source .venv/bin/activate
./farm-start.sh     # installs a launchd agent: runs in background, restarts on crash, starts at login
./farm-status.sh    # running/stopped + follow logs/bot.log
./farm-stop.sh      # stop and remove from login startup
```

Run `./farm-start.sh` again after editing `config.yaml`.

The service runs under `caffeinate`, so the Mac won't idle-sleep. Closing the lid still sleeps it, which pauses everything. For overnight runs, keep it plugged in with the lid open. The display can turn off.

## Configuration (`config.yaml`)

- `devices`: one entry per BlueStacks instance (`serial`, `max_marches`, optional per-farm `resources`)
- `resources` + `shuffle_resources`: what to gather and in what order
- `cycle_minutes`: random interval between checks
- `active_hours`: optional run window (commented out = 24/7)
- `thresholds`: per-template match cutoffs
- `routines`: timed side tasks, each with `every_minutes`, `retry_minutes` and `steps`
- `reset_taps`: buttons to tap when backing out (for example `world_button` in the city, so the bot never presses back there)
- `gather_sequence` and routine `steps` use the same step types:
  - `find`: tap a template. Options:
    - `optional`
    - `repeat: N` to keep tapping while the button is still there
    - `region` to search only part of the screen
    - `offset` to tap relative to the match
    - `scroll_if_missing` to swipe until the template appears
    - `tap_if_missing` to try other tabs first
  - `ensure` + `fix`: confirm a state (for example `level_6`). If it's missing, press buttons N times and re-check.
  - `tap_frac`: tap a screen position given as a fraction
  - `back`, `sleep`

## Templates (`templates/`)

| File | Screen |
|---|---|
| `search_button` | Magnifying glass, world map |
| `resource_wood` / `resource_food` / `resource_zent` | Lumberyard / Farmland / Mining Zone tabs |
| `level_6`, `level_plus`, `level_minus` | Level slider in the search panel |
| `search_go` | Blue Search button |
| `gather_button` | Gather on the tile popup |
| `march_button` | March on the deploy panel |
| `idle_squad` | "zZ" on an idle squad in the march queue |
| `home_map` | Headquarters button, meaning the world map is showing (tap it to enter the city) |
| `world_button` | World button in the city (tap it to return to the map) |
| `alliance_button`, `alliance_techs` | Alliance menu → Alliance Techs |
| `tech_thumbs` | Leader's recommended tech (thumbs-up badge) |
| `tab_combat`, `tab_dominator` | Alliance tech tabs |
| `donate_zent` | Blue zent Donate button (never the gem one) |
| `popup_close`, `back_arrow` | Close the tech popup, back out of menus |
| `collect_exp`, `collect_zent`, `collect_food` | City collection bubbles |

When a step fails, the bot saves a screenshot to `debug/`.

## To do

- Reconnect popup after the Mac wakes or the game drops its connection
- "Exit game?" popup handling
- Wood bubbles on the lumber yards (not captured yet)
- Optional fixed squad-to-resource pairing
- Second farm instance
