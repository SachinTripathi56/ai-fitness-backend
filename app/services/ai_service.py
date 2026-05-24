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
            logger.error(f"Workout generation error: {e}")
            raise RuntimeError(f"Failed to generate workout plan: {e}")

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
            logger.error(f"Diet generation error: {e}")
            raise RuntimeError(f"Failed to generate diet plan: {e}")

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
            logger.error(f"Schedule generation error: {e}")
            raise RuntimeError(f"Failed to generate schedule: {e}")

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
            logger.error(f"Chat error: {e}")
            raise RuntimeError(f"Chat service error: {e}")

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
