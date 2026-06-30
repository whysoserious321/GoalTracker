from flask import Flask, render_template, request, redirect, url_for
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE   = 'streak_data.json'
BACKUP_FILE = 'streak_data.json.bak'

# no_f and meditation are daily; weekly_cardio is weekly
DAILY_GOALS   = ['no_f', 'meditation']
WEEKLY_GOALS  = ['weekly_cardio']
GOALS         = DAILY_GOALS + WEEKLY_GOALS

GOAL_DISPLAY_NAMES = {
    'no_f':          'No F',
    'meditation':    'Meditation',
    'weekly_cardio': 'Weekly Cardio',
}


def load_data():
    if not os.path.exists(DATA_FILE):
        data = {'dates': {}, 'weeks': {}, 'click_data': {}}
        save_data(data)
        return data
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # streak_data.json was truncated/corrupted (e.g. an interrupted write or
        # power loss on the Pi). Fall back to the last known-good backup.
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, 'r') as f:
                data = json.load(f)
        else:
            raise
    if 'weeks' not in data:
        data['weeks'] = {}
    return data


def save_data(data):
    # Atomic write: serialise to a temp file in the same directory, fsync it, then
    # os.replace() onto the live file. An interrupted write can therefore never
    # leave a truncated streak_data.json. The previous good copy is kept as .bak.
    dir_name = os.path.dirname(os.path.abspath(DATA_FILE))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix='.streak_data_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(DATA_FILE):
            try:
                shutil.copy2(DATA_FILE, BACKUP_FILE)
            except OSError:
                pass
        os.replace(tmp_path, DATA_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_last_n_days(n):
    today = datetime.now().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def get_last_n_weeks(n):
    today = datetime.now().date()
    current_monday = today - timedelta(days=today.weekday())
    result = []
    for i in range(n - 1, -1, -1):
        week_start = current_monday - timedelta(weeks=i)
        week_end   = week_start + timedelta(days=6)
        result.append({
            'key':         week_start.isoformat(),
            'label':       f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}",
            'short_label': week_start.strftime('%b %d'),
        })
    return result


def calc_streaks(val_list):
    bool_list = [v for v in val_list if v is not None and v != 'skip']
    streaks, current = [], 0
    for achieved in bool_list:
        if achieved:
            current += 1
        else:
            if current > 0:
                streaks.append(current)
            current = 0
    if current > 0:
        streaks.append(current)
    return current, sorted(streaks, reverse=True)


@app.route('/', methods=['GET', 'POST'])
def index():
    data            = load_data()
    last_seven_days = get_last_n_days(7)
    last_four_weeks = get_last_n_weeks(4)

    if request.method == 'POST' and 'value' not in request.form:
        for date in last_seven_days:
            if date not in data['dates']:
                data['dates'][date] = {}
            for goal in DAILY_GOALS:
                val = request.form.get(f'{date}_{goal}', 'false')
                if val == 'true':
                    data['dates'][date][goal] = True
                elif val == 'skip':
                    data['dates'][date][goal] = 'skip'
                else:
                    data['dates'][date][goal] = False
        for week in last_four_weeks:
            wk = week['key']
            if wk not in data['weeks']:
                data['weeks'][wk] = {}
            for goal in WEEKLY_GOALS:
                val = request.form.get(f'{wk}_{goal}', 'false')
                if val == 'true':
                    data['weeks'][wk][goal] = True
                elif val == 'skip':
                    data['weeks'][wk][goal] = 'skip'
                else:
                    data['weeks'][wk][goal] = False
        save_data(data)
        return redirect(url_for('index'))

    streak_data            = {}
    percentages            = {}
    current_streaks        = {}
    longest_streaks        = {}
    second_longest_streaks = {}
    last_failures          = {}
    weekly_chart_data      = {}

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # ── Daily goals ───────────────────────────────────────────────────────
    all_dates = sorted(data['dates'].keys())
    for goal in DAILY_GOALS:
        dow      = {d: {'achieved': 0, 'total': 0} for d in day_names}
        val_list = [data['dates'][d].get(goal, None) for d in all_dates]
        cur, sorted_s = calc_streaks(val_list)

        current_streaks[goal]        = cur
        longest_streaks[goal]        = sorted_s[0] if sorted_s else 0
        second_longest_streaks[goal] = sorted_s[1] if len(sorted_s) > 1 else 0

        failures = []
        for date in reversed(all_dates):
            val = data['dates'][date].get(goal, None)
            if val is False:
                failures.append(date)
            if len(failures) >= 3:
                break
        last_failures[goal] = failures

        total_days, achieved_days = 0, 0
        for date in all_dates:
            val = data['dates'][date].get(goal, None)
            if val is not None and val != 'skip':
                total_days += 1
                if val is True:
                    achieved_days += 1
                day_name = day_names[datetime.fromisoformat(date).weekday()]
                dow[day_name]['total'] += 1
                if val is True:
                    dow[day_name]['achieved'] += 1

        percentages[goal] = (achieved_days / total_days * 100) if total_days else 0

        weekly_chart_data[goal] = []
        for day in day_names:
            d   = dow[day]
            pct = (d['achieved'] / d['total'] * 100) if d['total'] > 0 else None
            weekly_chart_data[goal].append({
                'day':          day,
                'percentage':   pct,
                'achieved':     d['achieved'],
                'not_achieved': d['total'] - d['achieved'],
            })

        streak_data[goal] = {
            date: data['dates'].get(date, {}).get(goal, None)
            for date in last_seven_days
        }

    # ── Weekly goals ──────────────────────────────────────────────────────
    all_weeks        = sorted(data['weeks'].keys())
    last_eight_weeks = get_last_n_weeks(8)
    for goal in WEEKLY_GOALS:
        val_list = [data['weeks'][wk].get(goal, None) for wk in all_weeks]
        cur, sorted_s = calc_streaks(val_list)

        current_streaks[goal]        = cur
        longest_streaks[goal]        = sorted_s[0] if sorted_s else 0
        second_longest_streaks[goal] = sorted_s[1] if len(sorted_s) > 1 else 0

        failures = []
        for wk in reversed(all_weeks):
            val = data['weeks'][wk].get(goal, None)
            if val is False:
                failures.append(wk)
            if len(failures) >= 3:
                break
        last_failures[goal] = failures

        recorded = [
            data['weeks'][wk].get(goal, None)
            for wk in all_weeks
            if data['weeks'][wk].get(goal, None) is not None
               and data['weeks'][wk].get(goal, None) != 'skip'
        ]
        total = len(recorded)
        percentages[goal] = (sum(recorded) / total * 100) if total else 0

        streak_data[goal] = {
            week['key']: data['weeks'].get(week['key'], {}).get(goal, None)
            for week in last_four_weeks
        }

        weekly_chart_data[goal] = []
        for week in last_eight_weeks:
            wk  = week['key']
            val = data['weeks'].get(wk, {}).get(goal, None)
            weekly_chart_data[goal].append({
                'day':          week['short_label'],
                'full_label':   week['label'],
                'achieved':     1 if val is True  else 0,
                'not_achieved': 1 if val is False else 0,
                'no_data':      1 if val is None  else 0,
                'skipped':      1 if val == 'skip' else 0,
            })

    # ── Click analysis (unchanged) ────────────────────────────────────────
    if 'click_data' not in data:
        data['click_data'] = {}

    current_year  = str(datetime.now().year)
    current_month = datetime.now().month
    click_sums    = {}

    for date_str, click_info in data['click_data'].items():
        if date_str.startswith(current_year):
            click_sums[date_str] = (
                click_info.get('1x',   0) * 1.0 +
                click_info.get('2x',   0) * 2.0 +
                click_info.get('0.5x', 0) * 0.5
            )

    total_sum   = sum(click_sums.values())
    average_sum = total_sum / current_month if current_month > 0 else 0

    return render_template(
        'index.html',
        last_seven_days        = last_seven_days,
        last_four_weeks        = last_four_weeks,
        streak_data            = streak_data,
        percentages            = percentages,
        goals                  = GOALS,
        daily_goals            = DAILY_GOALS,
        weekly_goals           = WEEKLY_GOALS,
        goal_display_names     = GOAL_DISPLAY_NAMES,
        current_streaks        = current_streaks,
        longest_streaks        = longest_streaks,
        second_longest_streaks = second_longest_streaks,
        last_failures          = last_failures,
        weekly_chart_data      = weekly_chart_data,
        click_sums             = click_sums,
        total_sum              = total_sum,
        average_sum            = average_sum,
    )


@app.route('/increment', methods=['POST'])
def increment():
    value = request.form.get('value')
    data  = load_data()
    today = str(datetime.now().date())

    if 'click_data' not in data:
        data['click_data'] = {}
    if today not in data['click_data']:
        data['click_data'][today] = {'1x': 0, '2x': 0, '0.5x': 0}

    if value == '1':
        data['click_data'][today]['1x']   += 1
    elif value == '2':
        data['click_data'][today]['2x']   += 1
    elif value == '0.5':
        data['click_data'][today]['0.5x'] += 1

    save_data(data)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)