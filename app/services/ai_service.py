"""
AI Service using Google Gemini 2.5 Flash (FREE tier).
Handles workout generation, diet planning, chat coaching,
schedule generation, and smart recommendations.

Get your FREE API key at: https://aistudio.google.com/app/apikey
Backend APIs are developed separately using FastAPI.
"""

import json
import asyncio
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from app.core.config import settings
from loguru import logger


class AIService:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = None

    def _get_model(self) -> genai.GenerativeModel:
        """Lazy-init Gemini model."""
        if self._model is None:
            self._model = genai.GenerativeModel(
                model_name=settings.GEMINI_MODEL,
                generation_config=genai.types.GenerationConfig(
                    temperature=settings.GEMINI_TEMPERATURE,
                    max_output_tokens=settings.GEMINI_MAX_TOKENS,
                ),
            )
        return self._model

    async def _generate(self, prompt: str, expect_json: bool = True) -> str:
        """
        Run a Gemini generation call in a thread pool
        (google-generativeai is sync, so we wrap it for async FastAPI).
        """
        def _sync_call():
            model = self._get_model()
            if expect_json:
                full_prompt = (
                    prompt
                    + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown fences, no extra text."
                )
            else:
                full_prompt = prompt
            response = model.generate_content(full_prompt)
            return response.text

        return await asyncio.get_event_loop().run_in_executor(None, _sync_call)

    def _parse_json(self, raw: str) -> dict | list:
        """Strip markdown fences if present and parse JSON."""
        text = raw.strip()
        if text.startswith("```"):
            # Remove ```json ... ``` wrapper
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        return json.loads(text)

    # ──────────────────────────────────────────────
    # FITNESS CALCULATIONS (no AI needed)
    # ──────────────────────────────────────────────

    def calculate_bmr(self, weight_kg: float, height_cm: float, age: int, gender: str) -> float:
        """Mifflin-St Jeor BMR formula."""
        if gender.lower() == "male":
            return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    def calculate_tdee(self, bmr: float, activity_level: str) -> float:
        multipliers = {
            "sedentary": 1.2,
            "lightly_active": 1.375,
            "moderately_active": 1.55,
            "very_active": 1.725,
            "extremely_active": 1.9,
        }
        return bmr * multipliers.get(activity_level, 1.55)

    def calculate_bmi(self, weight_kg: float, height_cm: float) -> float:
        return round(weight_kg / (height_cm / 100) ** 2, 1)

    def calculate_calorie_target(self, tdee: float, goal: str) -> int:
        adjustments = {
            "weight_loss": -500,
            "fat_loss": -400,
            "muscle_gain": +300,
            "maintenance": 0,
            "athletic_performance": +200,
        }
        return int(tdee + adjustments.get(goal, 0))

    def _build_user_context(self, profile: dict) -> str:
        lines = [
            "=== USER PROFILE ===",
            f"Age: {profile.get('age', 'unknown')}",
            f"Gender: {profile.get('gender', 'unknown')}",
            f"Height: {profile.get('height_cm', '?')} cm",
            f"Weight: {profile.get('weight_kg', '?')} kg",
            f"Goal: {profile.get('fitness_goal', 'general fitness')}",
            f"Activity Level: {profile.get('activity_level', 'moderate')}",
            f"Workout Experience: {profile.get('workout_experience', 'beginner')}",
            f"Workout Location: {profile.get('workout_location', 'home')}",
            f"Available Equipment: {', '.join(profile.get('available_equipment', []) or ['none'])}",
            f"Diet Type: {profile.get('diet_type', 'none specified')}",
            f"Allergies: {', '.join(profile.get('allergies', []) or ['none'])}",
            f"Medical Conditions: {', '.join(profile.get('medical_conditions', []) or ['none'])}",
            f"Daily Calorie Target: {profile.get('daily_calorie_target', 'to be calculated')}",
            f"Preferred Workout Days/Week: {profile.get('workout_days_per_week', 4)}",
            f"Preferred Workout Duration: {profile.get('workout_duration_minutes', 45)} min",
            "====================",
        ]
        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # WORKOUT GENERATION
    # ──────────────────────────────────────────────

    async def generate_workout_plan(
        self,
        user_profile: dict,
        weeks: int = 4,
        focus_areas: Optional[List[str]] = None,
    ) -> dict:
        """Generate a personalized progressive workout plan using Gemini."""
        ctx = self._build_user_context(user_profile)
        focus = f"Focus areas requested: {', '.join(focus_areas)}" if focus_areas else ""

        prompt = f"""You are an expert certified personal trainer.
Generate a safe, progressive {weeks}-week workout plan for this user.

{ctx}
{focus}

Return a JSON object with this EXACT structure:
{{
  "plan_name": "descriptive plan name",
  "description": "brief overview",
  "weeks": [
    {{
      "week_number": 1,
      "theme": "Foundation week description",
      "sessions": [
        {{
          "day_of_week": "monday",
          "session_name": "Upper Body Strength",
          "focus_area": "chest, shoulders, triceps",
          "estimated_duration_minutes": 45,
          "is_rest_day": false,
          "warmup_notes": "5 min light cardio + arm circles",
          "cooldown_notes": "5 min static chest/shoulder stretches",
          "exercises": [
            {{
              "name": "Push-ups",
              "category": "strength",
              "muscle_groups": ["chest", "triceps", "shoulders"],
              "equipment_needed": [],
              "sets": 3,
              "reps": "10-15",
              "rest_seconds": 60,
              "difficulty": "beginner",
              "instructions": "Keep core tight, lower chest to floor",
              "is_warmup": false,
              "is_cooldown": false,
              "progressive_note": "Add 2 reps each week"
            }}
          ]
        }}
      ]
    }}
  ],
  "progressive_overload_notes": "How to progress week by week",
  "recovery_recommendations": "Rest and recovery advice"
}}

Rules:
- Match equipment to user's available equipment EXACTLY
- Beginner = 3 sets, Intermediate = 4 sets, Advanced = 5 sets
- Include warmup and cooldown sessions
- Mark rest days with is_rest_day: true (no exercises needed)
- Be specific with exercise instructions"""

        try:
            raw = await self._generate(prompt)
            data = self._parse_json(raw)
            logger.info(f"Workout plan generated successfully")
            return data
        except Exception as e:
            logger.error(f"Workout generation error: {e}. Using local template fallback.")
            return {
                "plan_name": f"{user_profile.get('fitness_goal', 'Fitness').replace('_', ' ').title()} Plan",
                "description": "Personalized progressive training program tailored to your goals.",
                "weeks": [
                    {
                        "week_number": 1,
                        "theme": "Adaptation & Strength Foundation",
                        "sessions": [
                            {
                                "day_of_week": "monday",
                                "session_name": "Push Day — Chest, Shoulders & Triceps",
                                "focus_area": "chest, shoulders, triceps",
                                "estimated_duration_minutes": 45,
                                "is_rest_day": False,
                                "warmup_notes": "5 min light cardio + dynamic stretches",
                                "cooldown_notes": "5 min static stretching",
                                "exercises": [
                                    {
                                        "name": "Dumbbell Bench Press" if "dumbbells" in user_profile.get("available_equipment", []) else "Push-ups",
                                        "category": "strength",
                                        "muscle_groups": ["chest", "shoulders", "triceps"],
                                        "equipment_needed": ["dumbbells"] if "dumbbells" in user_profile.get("available_equipment", []) else [],
                                        "sets": 3,
                                        "reps": "10-12",
                                        "rest_seconds": 60,
                                        "difficulty": "beginner",
                                        "instructions": "Control the descent, push back up dynamically.",
                                        "is_warmup": False,
                                        "is_cooldown": False,
                                        "progressive_note": "Increase weight or reps slightly next week."
                                    },
                                    {
                                        "name": "Dumbbell Shoulder Press" if "dumbbells" in user_profile.get("available_equipment", []) else "Pike Pushups",
                                        "category": "strength",
                                        "muscle_groups": ["shoulders", "triceps"],
                                        "equipment_needed": ["dumbbells"] if "dumbbells" in user_profile.get("available_equipment", []) else [],
                                        "sets": 3,
                                        "reps": "10",
                                        "rest_seconds": 60,
                                        "difficulty": "medium",
                                        "instructions": "Press dumbbells overhead without arching the lower back.",
                                        "is_warmup": False,
                                        "is_cooldown": False,
                                        "progressive_note": "Keep form strict."
                                    }
                                ]
                            },
                            {
                                "day_of_week": "tuesday",
                                "session_name": "Active Recovery / Rest Day",
                                "focus_area": "recovery",
                                "estimated_duration_minutes": 0,
                                "is_rest_day": True,
                                "warmup_notes": "",
                                "cooldown_notes": "",
                                "exercises": []
                            },
                            {
                                "day_of_week": "wednesday",
                                "session_name": "Pull Day — Back & Biceps",
                                "focus_area": "back, biceps",
                                "estimated_duration_minutes": 45,
                                "is_rest_day": False,
                                "warmup_notes": "5 min dynamic warm up",
                                "cooldown_notes": "5 min static stretch",
                                "exercises": [
                                    {
                                        "name": "Dumbbell Rows" if "dumbbells" in user_profile.get("available_equipment", []) else "Pull-ups",
                                        "category": "strength",
                                        "muscle_groups": ["back", "biceps"],
                                        "equipment_needed": ["dumbbells"] if "dumbbells" in user_profile.get("available_equipment", []) else [],
                                        "sets": 3,
                                        "reps": "12",
                                        "rest_seconds": 60,
                                        "difficulty": "medium",
                                        "instructions": "Pull dumbbells to hip, squeeze shoulder blade.",
                                        "is_warmup": False,
                                        "is_cooldown": False,
                                        "progressive_note": "Increase weight next week."
                                    }
                                ]
                            },
                            {
                                "day_of_week": "thursday",
                                "session_name": "Active Recovery / Rest Day",
                                "focus_area": "recovery",
                                "estimated_duration_minutes": 0,
                                "is_rest_day": True,
                                "warmup_notes": "",
                                "cooldown_notes": "",
                                "exercises": []
                            },
                            {
                                "day_of_week": "friday",
                                "session_name": "Leg Day — Quad & Glute Focus",
                                "focus_area": "quads, glutes, hamstrings",
                                "estimated_duration_minutes": 45,
                                "is_rest_day": False,
                                "warmup_notes": "5 min leg swings and bodyweight squats",
                                "cooldown_notes": "5 min quad/hamstring stretches",
                                "exercises": [
                                    {
                                        "name": "Goblet Squats" if "dumbbells" in user_profile.get("available_equipment", []) else "Bodyweight Squats",
                                        "category": "strength",
                                        "muscle_groups": ["quads", "glutes"],
                                        "equipment_needed": ["dumbbells"] if "dumbbells" in user_profile.get("available_equipment", []) else [],
                                        "sets": 3,
                                        "reps": "12-15",
                                        "rest_seconds": 90,
                                        "difficulty": "medium",
                                        "instructions": "Squat down until thighs are parallel to ground.",
                                        "is_warmup": False,
                                        "is_cooldown": False,
                                        "progressive_note": "Add 2 reps next week."
                                    }
                                ]
                            },
                            {
                                "day_of_week": "saturday",
                                "session_name": "Rest Day",
                                "focus_area": "recovery",
                                "estimated_duration_minutes": 0,
                                "is_rest_day": True,
                                "warmup_notes": "",
                                "cooldown_notes": "",
                                "exercises": []
                            },
                            {
                                "day_of_week": "sunday",
                                "session_name": "Rest Day",
                                "focus_area": "recovery",
                                "estimated_duration_minutes": 0,
                                "is_rest_day": True,
                                "warmup_notes": "",
                                "cooldown_notes": "",
                                "exercises": []
                            }
                        ]
                    }
                ]
            }

    # ──────────────────────────────────────────────
    # DIET GENERATION
    # ──────────────────────────────────────────────

    async def generate_diet_plan(
        self,
        user_profile: dict,
        days: int = 7,
        calorie_override: Optional[int] = None,
        budget_preference: str = "moderate",
        cuisine_preference: str = "mixed",
    ) -> dict:
        """Generate a personalized meal plan using Gemini."""
        ctx = self._build_user_context(user_profile)
        cal_note = f"Override daily calories to: {calorie_override} kcal" if calorie_override else ""

        prompt = f"""You are an expert registered dietitian specializing in Indian and international nutrition.
Generate a detailed {days}-day meal plan for this user.

{ctx}
{cal_note}
Budget preference: {budget_preference}
Cuisine preference: {cuisine_preference}

Return a JSON object with this EXACT structure:
{{
  "plan_name": "My Personalized Nutrition Plan",
  "total_daily_calories": 2000,
  "macros": {{
    "protein_g": 150,
    "carbs_g": 200,
    "fat_g": 65
  }},
  "water_intake_ml": 2500,
  "days": [
    {{
      "day_of_week": "monday",
      "total_calories": 2000,
      "meals": [
        {{
          "meal_type": "breakfast",
          "name": "Masala Oats with Boiled Eggs",
          "suggested_time": "08:00",
          "total_calories": 420,
          "protein_g": 22,
          "carbs_g": 55,
          "fat_g": 10,
          "instructions": "Cook oats with veggies, season with cumin and coriander",
          "food_items": [
            {{
              "name": "Rolled Oats",
              "quantity_grams": 80,
              "calories": 300,
              "protein_g": 12,
              "carbs_g": 54,
              "fat_g": 6
            }}
          ]
        }}
      ]
    }}
  ],
  "grocery_list": [
    {{"item": "Rolled Oats", "quantity": "500g", "estimated_cost_inr": 80, "category": "grains"}}
  ],
  "meal_prep_tips": "Batch cook on Sunday for the week",
  "hydration_schedule": ["07:00 - 500ml water", "10:00 - 300ml water"]
}}

Rules:
- Strictly follow diet_type (vegetarian/vegan/keto/jain/non-veg)
- NEVER include allergens listed in the user profile
- Include Indian foods (dal, roti, rice, sabzi) when cuisine is mixed or indian
- Grocery costs in INR for Indian foods
- meal_type must be one of: breakfast, lunch, dinner, snack, pre_workout, post_workout"""

        try:
            raw = await self._generate(prompt)
            data = self._parse_json(raw)
            logger.info("Diet plan generated successfully")
            return data
        except Exception as e:
            logger.error(f"Diet generation error: {e}. Using local template fallback.")
            calorie_target = calorie_override or user_profile.get("daily_calorie_target") or 2000
            protein = round(user_profile.get("weight_kg", 70) * 1.8) if user_profile.get("weight_kg") else 120
            fat = round((calorie_target * 0.25) / 9)
            carbs = round((calorie_target - (protein * 4) - (fat * 9)) / 4)
            return {
                "plan_name": f"{user_profile.get('diet_type', 'Balanced').title()} Meal Plan",
                "total_daily_calories": calorie_target,
                "macros": {
                    "protein_g": protein,
                    "carbs_g": carbs,
                    "fat_g": fat
                },
                "water_intake_ml": 2500,
                "days": [
                    {
                        "day_of_week": day,
                        "total_calories": calorie_target,
                        "meals": [
                            {
                                "meal_type": "breakfast",
                                "name": "High Protein Oatmeal",
                                "suggested_time": "08:00",
                                "total_calories": round(calorie_target * 0.25),
                                "protein_g": round(protein * 0.25),
                                "carbs_g": round(carbs * 0.25),
                                "fat_g": round(fat * 0.25),
                                "instructions": "Mix oats with protein powder, milk, and top with fruits.",
                                "food_items": [
                                    {"name": "Oats", "quantity_grams": 50, "calories": 190, "protein_g": 6, "carbs_g": 33, "fat_g": 3},
                                    {"name": "Whey Protein", "quantity_grams": 30, "calories": 120, "protein_g": 24, "carbs_g": 2, "fat_g": 1.5}
                                ]
                            },
                            {
                                "meal_type": "lunch",
                                "name": "Grilled Chicken/Paneer Salad",
                                "suggested_time": "13:00",
                                "total_calories": round(calorie_target * 0.35),
                                "protein_g": round(protein * 0.35),
                                "carbs_g": round(carbs * 0.35),
                                "fat_g": round(fat * 0.35),
                                "instructions": "Toss greens, cucumbers, tomatoes with grilled chicken or paneer, and olive oil.",
                                "food_items": [
                                    {"name": "Chicken Breast" if user_profile.get("diet_type") != "vegetarian" else "Paneer", "quantity_grams": 150, "calories": 250, "protein_g": 35, "carbs_g": 2, "fat_g": 10}
                                ]
                            },
                            {
                                "meal_type": "snack",
                                "name": "Mixed Nuts & Fruits",
                                "suggested_time": "17:00",
                                "total_calories": round(calorie_target * 0.15),
                                "protein_g": round(protein * 0.1),
                                "carbs_g": round(carbs * 0.15),
                                "fat_g": round(fat * 0.2),
                                "instructions": "Eat a handful of raw nuts with an apple or biscuit.",
                                "food_items": [
                                    {"name": "Almonds", "quantity_grams": 20, "calories": 120, "protein_g": 4, "carbs_g": 4, "fat_g": 10}
                                ]
                            },
                            {
                                "meal_type": "dinner",
                                "name": "Baked Fish/Tofu with Rice & Veggies",
                                "suggested_time": "20:30",
                                "total_calories": round(calorie_target * 0.25),
                                "protein_g": round(protein * 0.3),
                                "carbs_g": round(carbs * 0.25),
                                "fat_g": round(fat * 0.2),
                                "instructions": "Bake tofu or fish with light spices. Serve with boiled rice and steamed broccoli.",
                                "food_items": [
                                    {"name": "Brown Rice", "quantity_grams": 100, "calories": 110, "protein_g": 2.5, "carbs_g": 23, "fat_g": 1}
                                ]
                            }
                        ]
                    } for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                ],
                "grocery_list": [
                    {"item": "Oats", "quantity": "500g", "estimated_cost_inr": 80, "category": "grains"},
                    {"item": "Whey Protein", "quantity": "1kg", "estimated_cost_inr": 2500, "category": "supplements"},
                    {"item": "Chicken Breast" if user_profile.get("diet_type") != "vegetarian" else "Paneer", "quantity": "1kg", "estimated_cost_inr": 400, "category": "protein"},
                    {"item": "Almonds", "quantity": "250g", "estimated_cost_inr": 250, "category": "nuts"},
                    {"item": "Brown Rice", "quantity": "1kg", "estimated_cost_inr": 90, "category": "grains"}
                ],
                "meal_prep_tips": "Wash and cut vegetables on Sunday for easy prep during the week.",
                "hydration_schedule": ["07:00 - 500ml water", "10:00 - 300ml water", "14:00 - 500ml water", "18:00 - 500ml water", "21:00 - 300ml water"]
            }

    # ──────────────────────────────────────────────
    # SMART SCHEDULE GENERATION
    # ──────────────────────────────────────────────

    async def generate_schedule(self, user_profile: dict) -> dict:
        """Generate a personalized weekly schedule using Gemini."""
        ctx = self._build_user_context(user_profile)

        prompt = f"""You are an expert life coach and daily planner.
Create an optimized, realistic weekly schedule balancing fitness, meals, work, and recovery.

{ctx}

Return a JSON object with this EXACT structure:
{{
  "schedule_name": "My Optimized Weekly Schedule",
  "days": [
    {{
      "day_of_week": "monday",
      "events": [
        {{
          "title": "Wake Up & Hydrate",
          "event_type": "lifestyle",
          "start_time": "06:30",
          "end_time": "06:45",
          "duration_minutes": 15,
          "description": "Drink 500ml water, light stretches",
          "is_reminder": true,
          "reminder_minutes_before": 0,
          "color": "#4CAF50",
          "order": 1
        }}
      ]
    }}
  ],
  "ai_reasoning": "Explanation of why this schedule was designed this way"
}}

Event type options: workout, meal, hydration, sleep, meditation, work, recovery, lifestyle
Color guide:
  workout = "#FF6B35"
  meal = "#4CAF50"
  hydration = "#2196F3"
  sleep = "#9C27B0"
  meditation = "#00BCD4"
  work = "#607D8B"
  recovery = "#FF9800"
  lifestyle = "#795548"

Rules:
- Base wake/sleep times on user profile preferences
- Space meals 3-4 hours apart
- Place workout at preferred_workout_time
- Include pre and post workout meals around workout time
- Add water reminders every 2 hours
- Include a wind-down routine before sleep
- Generate all 7 days (monday through sunday)"""

        try:
            raw = await self._generate(prompt)
            data = self._parse_json(raw)
            logger.info("Schedule generated successfully")
            return data
        except Exception as e:
            logger.error(f"Schedule generation error: {e}. Using local template fallback.")
            wake_time = user_profile.get("wake_up_time") or "06:30"
            sleep_time = user_profile.get("sleep_time") or "22:30"
            return {
                "schedule_name": "Standard Daily Fitness Schedule",
                "days": [
                    {
                        "day_of_week": day,
                        "events": [
                            {
                                "title": "Wake Up & Hydrate",
                                "event_type": "lifestyle",
                                "start_time": wake_time,
                                "end_time": f"{wake_time[:2]}:15",
                                "duration_minutes": 15,
                                "description": "Drink 500ml water, stretch",
                                "is_reminder": True,
                                "reminder_minutes_before": 0,
                                "color": "#4CAF50",
                                "order": 1
                            },
                            {
                                "title": "Breakfast",
                                "event_type": "meal",
                                "start_time": "08:00",
                                "end_time": "08:30",
                                "duration_minutes": 30,
                                "description": "High protein breakfast",
                                "is_reminder": False,
                                "color": "#4CAF50",
                                "order": 2
                            },
                            {
                                "title": "Hydration Reminder",
                                "event_type": "hydration",
                                "start_time": "11:00",
                                "end_time": "11:05",
                                "duration_minutes": 5,
                                "description": "Drink 300ml water",
                                "is_reminder": True,
                                "color": "#2196F3",
                                "order": 3
                            },
                            {
                                "title": "Lunch",
                                "event_type": "meal",
                                "start_time": "13:00",
                                "end_time": "13:30",
                                "duration_minutes": 30,
                                "description": "Balanced lunch",
                                "is_reminder": False,
                                "color": "#4CAF50",
                                "order": 4
                            },
                            {
                                "title": "Workout Session",
                                "event_type": "workout",
                                "start_time": "18:00",
                                "end_time": "19:00",
                                "duration_minutes": 60,
                                "description": "Daily workout plan",
                                "is_reminder": False,
                                "color": "#FF6B35",
                                "order": 5
                            },
                            {
                                "title": "Dinner",
                                "event_type": "meal",
                                "start_time": "20:30",
                                "end_time": "21:00",
                                "duration_minutes": 30,
                                "description": "Post-workout recovery dinner",
                                "is_reminder": False,
                                "color": "#4CAF50",
                                "order": 6
                            },
                            {
                                "title": "Wind down & Sleep",
                                "event_type": "sleep",
                                "start_time": sleep_time,
                                "end_time": wake_time,
                                "duration_minutes": 480,
                                "description": "Aim for 8 hours of restful sleep",
                                "is_reminder": False,
                                "color": "#9C27B0",
                                "order": 7
                            }
                        ]
                    } for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                ],
                "ai_reasoning": "Standard daily schedule structure optimized for balanced activity, nutrition, and recovery."
            }

    # ──────────────────────────────────────────────
    # AI CHAT ASSISTANT
    # ──────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        user_profile: dict,
    ) -> Dict[str, Any]:
        """
        Conversational AI fitness coach using Gemini with memory.
        """
        ctx = self._build_user_context(user_profile)

        # Build conversation context string
        history_text = ""
        for msg in conversation_history[-8:]:  # last 8 messages for context
            role = "User" if msg["role"] == "user" else "Coach"
            history_text += f"{role}: {msg['content']}\n"

        prompt = f"""You are an expert AI fitness coach, nutritionist, and lifestyle mentor.
Be friendly, motivating, evidence-based, and always personalize your advice.
For medical concerns, recommend consulting a doctor.

{ctx}

Previous conversation:
{history_text}

User: {user_message}
Coach:"""

        def _sync_chat():
            model = self._get_model()
            response = model.generate_content(prompt)
            return response.text

        try:
            reply = await asyncio.get_event_loop().run_in_executor(None, _sync_chat)
            suggestions = await self._generate_suggestions(user_message, reply)
            return {
                "reply": reply.strip(),
                "tokens_used": len(reply.split()),  # approximate
                "suggested_prompts": suggestions,
            }
        except Exception as e:
            logger.error(f"Chat error: {e}. Using offline fallback.")
            return {
                "reply": "I'm currently running in offline recovery mode because the AI model is temporarily unreachable. Let's keep focusing on your goals! What details would you like to discuss about your workouts or diet today?",
                "tokens_used": 30,
                "suggested_prompts": [
                    "Give me a home workout for today",
                    "What should I eat after my workout?",
                    "How much protein do I need daily?"
                ],
            }

    async def _generate_suggestions(self, user_msg: str, ai_reply: str) -> List[str]:
        """Generate 3 follow-up prompt suggestions."""
        prompt = f"""Based on this fitness conversation, suggest exactly 3 short follow-up questions.
User asked: "{user_msg}"
Coach replied: "{ai_reply[:150]}"

Return a JSON object like: {{"suggestions": ["question 1", "question 2", "question 3"]}}
Each question must be under 60 characters."""

        try:
            raw = await self._generate(prompt)
            data = self._parse_json(raw)
            return data.get("suggestions", [])[:3]
        except Exception:
            return [
                "What should I eat post-workout?",
                "Can you adjust my plan?",
                "How do I track my progress?",
            ]

    # ──────────────────────────────────────────────
    # AI RECOMMENDATIONS
    # ──────────────────────────────────────────────

    async def generate_recommendations(
        self,
        user_profile: dict,
        progress_data: dict,
    ) -> List[Dict[str, Any]]:
        """Analyze progress and generate smart actionable recommendations."""
        ctx = self._build_user_context(user_profile)

        prompt = f"""You are an expert AI fitness analyst.
Analyze this user's progress data and generate 3-5 actionable recommendations.

{ctx}

Recent Progress Data:
- Current weight: {progress_data.get('current_weight', 'unknown')} kg
- Starting weight: {progress_data.get('starting_weight', 'unknown')} kg
- Workout completion rate: {progress_data.get('completion_rate', 'unknown')}%
- Average sleep: {progress_data.get('avg_sleep', 'unknown')} hours/night
- Average steps: {progress_data.get('avg_steps', 'unknown')}/day
- Current streak: {progress_data.get('streak', 0)} days

Return a JSON object:
{{
  "recommendations": [
    {{
      "type": "workout",
      "title": "Short title (max 8 words)",
      "content": "Detailed, actionable advice (2-3 sentences)",
      "priority": "high"
    }}
  ]
}}

type must be one of: workout, diet, recovery, lifestyle, motivation
priority must be: high, medium, or low"""

        try:
            raw = await self._generate(prompt)
            data = self._parse_json(raw)
            return data.get("recommendations", [])
        except Exception as e:
            logger.error(f"Recommendation generation error: {e}")
            return []

    # ──────────────────────────────────────────────
    # ADAPTIVE SCHEDULE
    # ──────────────────────────────────────────────

    async def adapt_schedule(
        self,
        user_profile: dict,
        event_type: str,
        context: dict,
    ) -> Dict[str, Any]:
        """
        Adaptive schedule intelligence:
        missed_workout → reschedule
        extra_calories → balance meals
        fatigue → suggest recovery
        """
        prompt = f"""You are an adaptive AI fitness coach.
The user experienced: {event_type}
Context: {json.dumps(context)}
User goal: {user_profile.get('fitness_goal', 'general fitness')}

Generate an adaptive response. Return JSON:
{{
  "action": "reschedule|reduce_intensity|rest|balance_calories",
  "reason": "Brief explanation",
  "adjusted_events": [],
  "message_to_user": "Short motivating message (1-2 sentences)"
}}"""

        try:
            raw = await self._generate(prompt)
            return self._parse_json(raw)
        except Exception as e:
            logger.error(f"Adaptive schedule error: {e}")
            return {
                "action": "rest",
                "reason": "Unable to analyze",
                "adjusted_events": [],
                "message_to_user": "Take it easy today — consistency matters more than perfection!",
            }


ai_service = AIService()
