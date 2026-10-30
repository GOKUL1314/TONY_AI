"""
Routine Management and Execution Subsystem for TONY AI Personalization (Stage 12).
Manages multi-step daily or contextual routines (morning, study, evening)
while strictly adhering to Stage 5 and Stage 10 confirmation policies.
"""
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from personalization.models import Routine, RoutineStep, RecurrenceType
from personalization.storage import PersonalizationDatabase
from personalization.policy import PersonalizationPolicy
from personalization.errors import RoutineNotFoundError, ConsequentialActionBlockedError

logger = logging.getLogger("tony.personalization.routines")


class RoutineManager:
    """Manages creation, scheduling, and safe execution of defined routines."""

    def __init__(self, db: PersonalizationDatabase):
        self.db = db
        self._ensure_default_routines()

    def _ensure_default_routines(self):
        """Seed initial default routines if not present."""
        if not self.db.list_routines():
            morning = Routine(
                id="rtn_morning_default",
                name="Morning Routine",
                description="Daily morning briefing and schedule review",
                steps=[
                    RoutineStep(step_id="step_1", action_type="briefing", description="Generate daily morning briefing"),
                    RoutineStep(step_id="step_2", action_type="check_reminders", description="Review today's pending reminders")
                ],
                schedule_time="08:00",
                recurrence=RecurrenceType.DAILY,
                enabled=True
            )
            self.db.save_routine(morning)

            evening = Routine(
                id="rtn_evening_default",
                name="Evening Routine",
                description="End-of-day summary and completed task recap",
                steps=[
                    RoutineStep(step_id="step_1", action_type="evening_summary", description="Generate daily evening summary")
                ],
                schedule_time="21:00",
                recurrence=RecurrenceType.DAILY,
                enabled=True
            )
            self.db.save_routine(evening)

            study = Routine(
                id="rtn_study_default",
                name="Study Routine",
                description="Focus mode activation and study session check",
                steps=[
                    RoutineStep(step_id="step_1", action_type="focus_mode", description="Set focus mode preference"),
                    RoutineStep(step_id="step_2", action_type="check_reminders", description="Check study bookmarks")
                ],
                schedule_time="14:00",
                recurrence=RecurrenceType.NONE,
                enabled=True
            )
            self.db.save_routine(study)

    def create_routine(
        self,
        name: str,
        description: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
        schedule_time: Optional[str] = None,
        recurrence: RecurrenceType = RecurrenceType.NONE
    ) -> Routine:
        """Define a new routine with sequential steps."""
        rtn_id = f"rtn_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        step_objs = []
        if steps:
            for idx, s in enumerate(steps):
                step_objs.append(RoutineStep(
                    step_id=s.get("step_id", f"s_{idx+1}"),
                    action_type=s.get("action_type", ""),
                    parameters=s.get("parameters", {}),
                    description=s.get("description", "")
                ))

        routine = Routine(
            id=rtn_id,
            name=name.strip(),
            description=description.strip(),
            steps=step_objs,
            schedule_time=schedule_time,
            recurrence=recurrence,
            enabled=True
        )

        saved = self.db.save_routine(routine)
        self.db.log_audit("routine_created", {"id": rtn_id, "name": name, "steps_count": len(step_objs)})
        logger.info(f"Created routine '{name}' (id: {rtn_id}) with {len(step_objs)} steps.")
        return saved

    def get_routine(self, routine_id: str) -> Optional[Routine]:
        """Fetch routine by ID or case-insensitive name/slug."""
        rtn = self.db.get_routine(routine_id)
        if rtn:
            return rtn
        clean = routine_id.lower().replace("_", " ").strip()
        for r in self.db.list_routines():
            if r.name.lower() == clean or routine_id.lower() in r.id.lower() or clean in r.name.lower():
                return r
        return None

    def list_routines(self, enabled_only: bool = False) -> List[Routine]:
        """List stored routines."""
        return self.db.list_routines(enabled_only=enabled_only)

    def delete_routine(self, routine_id: str) -> bool:
        """Delete a routine."""
        ok = self.db.delete_routine(routine_id)
        if ok:
            self.db.log_audit("routine_deleted", {"id": routine_id})
        return ok

    def run_routine(
        self,
        routine_id: str,
        briefing_generator=None,
        tool_executor=None,
        notification_service=None
    ) -> Dict[str, Any]:
        """
        Execute the steps in a routine sequentially.
        Enforces consequential action blocks and tool confirmation checks.
        """
        routine = self.get_routine(routine_id)
        if not routine:
            raise RoutineNotFoundError(f"Routine '{routine_id}' not found.")

        results = []
        for step in routine.steps:
            step_res = {"step_id": step.step_id, "action_type": step.action_type, "status": "success"}

            # Check consequential action policy
            try:
                PersonalizationPolicy.check_consequential_action(step.action_type, step.parameters)
            except ConsequentialActionBlockedError as c_err:
                step_res["status"] = "blocked"
                step_res["error"] = str(c_err)
                results.append(step_res)
                continue

            # Execute based on step type
            if step.action_type == "briefing" and briefing_generator:
                b_data = briefing_generator.generate_morning_briefing()
                step_res["result"] = b_data.synthesized_text
            elif step.action_type == "evening_summary" and briefing_generator:
                s_data = briefing_generator.generate_evening_summary()
                step_res["result"] = s_data.synthesized_text
            elif step.action_type == "check_reminders":
                rems = self.db.list_reminders(enabled_only=True)
                step_res["result"] = f"{len(rems)} active reminders."
            elif step.action_type == "tool_execution" and tool_executor:
                plan_dict = {"tool": step.parameters.get("tool"), "parameters": step.parameters.get("parameters", {})}
                t_res = tool_executor.execute_plan(plan_dict)
                step_res["result"] = t_res.to_dict()
                if not t_res.success:
                    step_res["status"] = "failed"
            else:
                step_res["result"] = f"Processed step: {step.description or step.action_type}"

            results.append(step_res)

        self.db.log_audit("routine_executed", {"id": routine.id, "name": routine.name, "results": results})
        logger.info(f"Executed routine '{routine.name}' ({len(results)} steps).")
        return {
            "status": "success",
            "routine": routine.name,
            "routine_id": routine.id,
            "routine_name": routine.name,
            "executed_at": datetime.now().isoformat(),
            "executed_steps": results,
            "steps": results
        }
