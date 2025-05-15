from flask import Flask, render_template, request, redirect, url_for
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_FILE = 'streak_data.json'
GOALS = ['step_count', 'meditation']

def load_data():
    if not os.path.exists(DATA_FILE):
        data = {'dates': {}}
        save_data(data)
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_last_n_days(n):
    today = datetime.now().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]

@app.route('/', methods=['GET', 'POST'])
def index():
    data = load_data()
    last_seven_days = get_last_n_days(7)

    # Update daily checkboxes if "Update" button is clicked
    if request.method == 'POST' and 'value' not in request.form:
        for date in last_seven_days:
            if date not in data['dates']:
                data['dates'][date] = {}
            for goal in GOALS:
                achieved = request.form.get(f'{date}_{goal}') == 'on'
                data['dates'][date][goal] = achieved
        save_data(data)
        return redirect(url_for('index'))

    # Build all the goal-related data
    streak_data = {}
    percentages = {}
    current_streaks = {}
    longest_streaks = {}
    second_longest_streaks = {}
    last_failures = {}
    day_of_week_data = {}
    weekly_chart_data = {}

    for goal in GOALS:
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_of_week_data[goal] = {day: {'achieved': 0, 'total': 0} for day in day_names}

        # Collect all dates in chronological order
        all_dates = sorted(data['dates'].keys())
        streaks = []
        current_streak = 0

        # Calculate streaks
        for date in all_dates:
            achieved = data['dates'][date].get(goal, False)
            if achieved:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        if current_streak > 0:
            streaks.append(current_streak)

        sorted_streaks = sorted(streaks, reverse=True)
        longest_streaks[goal] = sorted_streaks[0] if len(sorted_streaks) > 0 else 0
        second_longest_streaks[goal] = sorted_streaks[1] if len(sorted_streaks) > 1 else 0
        current_streaks[goal] = current_streak

        # Last 3 failures
        failures = []
        for date in reversed(all_dates):
            achieved = data['dates'][date].get(goal, None)
            if achieved is False:
                failures.append(date)
            if len(failures) >= 3:
                break
        last_failures[goal] = failures

        # Percentage calculation
        total_days = 0
        achieved_days = 0
        for date in data['dates']:
            achieved_flag = data['dates'][date].get(goal, None)
            if achieved_flag is not None:
                total_days += 1
                if achieved_flag:
                    achieved_days += 1

                # Map each date to day of the week
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                day_name = date_obj.strftime('%A')
                dow_data = day_of_week_data[goal][day_name]
                dow_data['total'] += 1
                if achieved_flag:
                    dow_data['achieved'] += 1

        percentage = (achieved_days / total_days * 100) if total_days else 0
        percentages[goal] = percentage

        # Weekly chart data
        for day in day_names:
            dow_data = day_of_week_data[goal][day]
            if dow_data['total'] > 0:
                day_percentage = dow_data['achieved'] / dow_data['total'] * 100
            else:
                day_percentage = None
            weekly_chart_data.setdefault(goal, []).append({
                'day': day,
                'percentage': day_percentage,
                'achieved': dow_data['achieved'],
                'not_achieved': dow_data['total'] - dow_data['achieved'],
            })

        # Prepare streak_data for the last seven days
        streak_data[goal] = {
            date: data['dates'].get(date, {}).get(goal, False)
            for date in last_seven_days
        }

    # --- Summation/Click Data Analysis ---
    if 'click_data' not in data:
        data['click_data'] = {}

    click_sums = {}
    # Gather click sums and collect unique months
    unique_months = set()
    for date_str, click_info in data['click_data'].items():
        # Parse the date and add the year-month string to the set
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        unique_months.add(date_obj.strftime('%Y-%m'))
        # Calculate sum for each date
        day_sum = (
            click_info.get('1x', 0) * 1.0 +
            click_info.get('2x', 0) * 2.0 +
            click_info.get('0.5x', 0) * 0.5
        )
        click_sums[date_str] = day_sum

    total_sum = sum(click_sums.values())
    num_months = len(unique_months)
    
    # Compute average per month
    average_sum = total_sum / num_months if num_months > 0 else 0

    return render_template(
        'index.html',
        last_seven_days=last_seven_days,
        streak_data=streak_data,
        percentages=percentages,
        goals=GOALS,
        current_streaks=current_streaks,
        longest_streaks=longest_streaks,
        second_longest_streaks=second_longest_streaks,
        last_failures=last_failures,
        weekly_chart_data=weekly_chart_data,
        click_sums=click_sums,
        total_sum=total_sum,
        average_sum=average_sum
    )

@app.route('/increment', methods=['POST'])
def increment():
    value = request.form.get('value')  # '1', '2', or '0.5'
    data = load_data()
    today = str(datetime.now().date())

    if 'click_data' not in data:
        data['click_data'] = {}
    if today not in data['click_data']:
        data['click_data'][today] = {
            '1x': 0,
            '2x': 0,
            '0.5x': 0
        }

    if value == '1':
        data['click_data'][today]['1x'] += 1
    elif value == '2':
        data['click_data'][today]['2x'] += 1
    elif value == '0.5':
        data['click_data'][today]['0.5x'] += 1

    save_data(data)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
