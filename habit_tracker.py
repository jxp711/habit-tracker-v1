from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional
import uuid

DATA_DIR = "data"
DATA_PATH = os.path.join(DATA_DIR, "habits.json")
SCHEMA_VERSION = 1


# ---------- Utilities ----------

def today_iso() -> str:
    return date.today().isoformat()

def parse_iso(d: str) -> date:
    return date.fromisoformat(d)

def clear_screen() -> None:
    # Polite CLI: optional clear
    os.system("cls" if os.name == "nt" else "clear")

def prompt_enter() -> None:
    input("\nPress Enter to continue...")

def ask_choice(prompt: str, choices: List[str]) -> str:
    """Return a validated choice from a list of allowed strings."""
    choices_lower = [c.lower() for c in choices]
    while True:
        raw = input(prompt).strip().lower()
        if raw in choices_lower:
            return raw
        print(f"Please enter one of: {', '.join(choices)}")

def ask_nonempty(prompt: str, max_len: int = 50) -> str:
    while True:
        s = input(prompt).strip()
        if not s:
            print("Input cannot be empty.")
            continue
        if len(s) > max_len:
            print(f"Please keep it under {max_len} characters.")
            continue
        return s


# ---------- Data Model ----------

@dataclass
class Habit:
    id: str
    name: str
    created_at: str  # ISO date
    completions: List[str]  # list of ISO dates (unique)

    def completion_set(self) -> set[str]:
        return set(self.completions)

    def is_completed_on(self, iso_day: str) -> bool:
        return iso_day in self.completion_set()

    def mark_complete(self, iso_day: str) -> bool:
        s = self.completion_set()
        if iso_day in s:
            return False
        s.add(iso_day)
        self.completions = sorted(s)
        return True

    def unmark_complete(self, iso_day: str) -> bool:
        s = self.completion_set()
        if iso_day not in s:
            return False
        s.remove(iso_day)
        self.completions = sorted(s)
        return True


# ---------- Persistence ----------

def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

def default_store() -> Dict:
    return {"version": SCHEMA_VERSION, "habits": []}

def load_store() -> Dict:
    ensure_data_dir()
    if not os.path.exists(DATA_PATH):
        return default_store()

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            store = json.load(f)
    except (json.JSONDecodeError, OSError):
        # If file is corrupted, don't crash. Start fresh but keep a backup.
        backup = DATA_PATH + ".bak"
        try:
            os.replace(DATA_PATH, backup)
            print(f"Warning: data file was corrupted. Backed up to {backup}")
        except OSError:
            pass
        return default_store()

    if not isinstance(store, dict) or "habits" not in store:
        return default_store()

    # Minimal version handling
    if store.get("version") != SCHEMA_VERSION:
        # For v1, we'll accept older versions if format matches.
        store["version"] = SCHEMA_VERSION

    if not isinstance(store["habits"], list):
        store["habits"] = []

    return store

def save_store(store: Dict) -> None:
    ensure_data_dir()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)

def habits_from_store(store: Dict) -> List[Habit]:
    habits = []
    for h in store.get("habits", []):
        if not isinstance(h, dict):
            continue
        habits.append(
            Habit(
                id=str(h.get("id", "")),
                name=str(h.get("name", "")),
                created_at=str(h.get("created_at", today_iso())),
                completions=list(h.get("completions", [])),
            )
        )
    # Drop broken entries (no id/name)
    habits = [h for h in habits if h.id and h.name]
    return habits

def store_from_habits(habits: List[Habit]) -> Dict:
    return {"version": SCHEMA_VERSION, "habits": [asdict(h) for h in habits]}


# ---------- Core Logic ----------

def find_habit(habits: List[Habit], habit_id: str) -> Optional[Habit]:
    for h in habits:
        if h.id == habit_id:
            return h
    return None

def current_streak(habit: Habit, ref: Optional[date] = None) -> int:
    """Count consecutive days completed ending at ref (default today),
    allowing streak to end at today if completed today, otherwise yesterday if not."""
    if ref is None:
        ref = date.today()

    completed = habit.completion_set()
    if not completed:
        return 0

    # Determine the starting day to count from: today if done, else yesterday.
    start = ref
    if start.isoformat() not in completed:
        start = ref - timedelta(days=1)

    streak = 0
    day = start
    while day.isoformat() in completed:
        streak += 1
        day -= timedelta(days=1)

    return streak

def weekly_summary(habit: Habit, ref: Optional[date] = None) -> int:
    """Count completions in last 7 days including ref day."""
    if ref is None:
        ref = date.today()
    completed = habit.completion_set()
    days = [(ref - timedelta(days=i)).isoformat() for i in range(7)]
    return sum(1 for d in days if d in completed)


# ---------- CLI UI ----------

def print_header(title: str) -> None:
    print("=" * 40)
    print(title)
    print("=" * 40)

def choose_habit(habits: List[Habit]) -> Optional[Habit]:
    if not habits:
        print("No habits yet. Add one first.")
        return None

    print("\nHabits:")
    for i, h in enumerate(habits, start=1):
        print(f"  {i}. {h.name}")

    while True:
        raw = input("\nSelect a habit number (or Enter to cancel): ").strip()
        if raw == "":
            return None
        if not raw.isdigit():
            print("Please enter a number.")
            continue
        idx = int(raw)
        if 1 <= idx <= len(habits):
            return habits[idx - 1]
        print("That number is out of range.")

def action_list(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Your Habits")
    if not habits:
        print("No habits yet.")
        return

    t = today_iso()
    for h in habits:
        done = "✅" if h.is_completed_on(t) else "—"
        streak = current_streak(h)
        print(f"- {h.name}  [{done}]  Streak: {streak}")

def action_add(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Add a Habit")
    name = ask_nonempty("Habit name: ")

    # Prevent duplicates by name (case-insensitive)
    if any(h.name.lower() == name.lower() for h in habits):
        print("A habit with that name already exists.")
        return

    h = Habit(
        id=uuid.uuid4().hex[:8],
        name=name,
        created_at=today_iso(),
        completions=[],
    )
    habits.append(h)
    print(f"Added habit: {h.name}")

def action_mark_today(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Mark Habit Complete (Today)")
    h = choose_habit(habits)
    if not h:
        return
    if h.mark_complete(today_iso()):
        print(f"Marked '{h.name}' complete for today.")
    else:
        print(f"'{h.name}' is already marked complete today.")

def action_unmark_today(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Undo Today Completion")
    h = choose_habit(habits)
    if not h:
        return
    if h.unmark_complete(today_iso()):
        print(f"Unmarked '{h.name}' for today.")
    else:
        print(f"'{h.name}' was not marked complete today.")

def action_details(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Habit Details")
    h = choose_habit(habits)
    if not h:
        return

    streak = current_streak(h)
    t = today_iso()
    done_today = h.is_completed_on(t)

    print(f"\nName: {h.name}")
    print(f"Created: {h.created_at}")
    print(f"Done today: {'Yes' if done_today else 'No'}")
    print(f"Current streak: {streak}")

    last7 = [ (date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1) ]
    print("\nLast 7 days:")
    for d in last7:
        mark = "✅" if d in h.completion_set() else "—"
        print(f"  {d}: {mark}")

def action_weekly_summary(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Weekly Summary (Last 7 Days)")
    if not habits:
        print("No habits yet.")
        return

    for h in habits:
        hits = weekly_summary(h)
        print(f"- {h.name}: {hits}/7 days")

def action_delete(habits: List[Habit]) -> None:
    clear_screen()
    print_header("Delete a Habit")
    h = choose_habit(habits)
    if not h:
        return
    confirm = ask_choice(f"Delete '{h.name}'? (y/n): ", ["y", "n"])
    if confirm == "y":
        habits.remove(h)
        print("Deleted.")
    else:
        print("Cancelled.")


def main() -> None:
    store = load_store()
    habits = habits_from_store(store)

    while True:
        clear_screen()
        print_header("Habit Tracker v1")
        print("1) List habits")
        print("2) Add habit")
        print("3) Mark habit complete (today)")
        print("4) Undo today completion")
        print("5) Habit details")
        print("6) Weekly summary")
        print("7) Delete habit")
        print("0) Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            action_list(habits)
            prompt_enter()
        elif choice == "2":
            action_add(habits)
            save_store(store_from_habits(habits))
            prompt_enter()
        elif choice == "3":
            action_mark_today(habits)
            save_store(store_from_habits(habits))
            prompt_enter()
        elif choice == "4":
            action_unmark_today(habits)
            save_store(store_from_habits(habits))
            prompt_enter()
        elif choice == "5":
            action_details(habits)
            prompt_enter()
        elif choice == "6":
            action_weekly_summary(habits)
            prompt_enter()
        elif choice == "7":
            action_delete(habits)
            save_store(store_from_habits(habits))
            prompt_enter()
        elif choice == "0":
            # Autosave on exit too
            save_store(store_from_habits(habits))
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")
            prompt_enter()


if __name__ == "__main__":
    main()
