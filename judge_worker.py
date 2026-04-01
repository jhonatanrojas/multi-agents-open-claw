#!/usr/bin/env python3
"""
judge_worker.py - JUDGE as formal agent (F2.6)

JUDGE is a read-only evaluator that never modifies files.
Evaluates against 4 dimensions:
1. Acceptance criteria compliance
2. Interface consistency
3. Contracts compliance
4. Obvious defects
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from agent_worker import AgentWorker, WorkerResult
from task_entity import TaskEntity, TaskStatus


class JudgeVerdict(str, Enum):
    """JUDGE verdict options."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_INFO = "NEEDS_INFO"


class EvaluationDimension(str, Enum):
    """Evaluation dimensions for JUDGE."""
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    INTERFACE_CONSISTENCY = "interface_consistency"
    CONTRACTS_COMPLIANCE = "contracts_compliance"
    DEFECTS = "defects"


@dataclass
class JudgeEvaluation:
    """Complete evaluation result from JUDGE."""
    verdict: JudgeVerdict
    reason: str
    dimension: Optional[EvaluationDimension]
    score: float  # 0-1
    issues: List[str]
    recommendations: List[str]


class JudgeWorker(AgentWorker):
    """
    JUDGE agent worker - formal quality evaluator.
    
    Read-only evaluator that never modifies files.
    Automatically spawned by supervisor before marking tasks as done.
    """
    
    def __init__(self):
        super().__init__("judge")
        self.evaluation_dimensions = [
            EvaluationDimension.ACCEPTANCE_CRITERIA,
            EvaluationDimension.INTERFACE_CONSISTENCY,
            EvaluationDimension.CONTRACTS_COMPLIANCE,
            EvaluationDimension.DEFECTS,
        ]
    
    def evaluate(
        self,
        task: TaskEntity,
        work_output: Dict[str, Any],
        acceptance_criteria: Optional[List[str]] = None
    ) -> JudgeEvaluation:
        """
        Evaluate work against all dimensions.
        
        Args:
            task: Original task
            work_output: Output from worker agent
            acceptance_criteria: Criteria to check against
        
        Returns:
            JudgeEvaluation with verdict and details
        """
        issues = []
        recommendations = []
        
        # Dimension 1: Acceptance criteria
        if acceptance_criteria:
            missing = self._check_acceptance_criteria(work_output, acceptance_criteria)
            if missing:
                issues.append(f"Missing acceptance criteria: {missing}")
        
        # Dimension 2: Interface consistency
        consistency_issues = self._check_interface_consistency(work_output)
        issues.extend(consistency_issues)
        
        # Dimension 3: Contracts compliance
        contract_issues = self._check_contracts_compliance(work_output)
        issues.extend(contract_issues)
        
        # Dimension 4: Obvious defects
        defects = self._check_defects(work_output)
        issues.extend(defects)
        
        # Calculate score
        score = self._calculate_score(issues, acceptance_criteria)
        
        # Determine verdict
        if score >= 0.85 and not issues:
            verdict = JudgeVerdict.APPROVED
            reason = "Work meets all quality standards"
        elif score >= 0.70:
            verdict = JudgeVerdict.NEEDS_INFO
            reason = "Work acceptable but has minor issues"
        else:
            verdict = JudgeVerdict.REJECTED
            reason = f"Quality below threshold: {issues[0] if issues else 'unknown'}"
        
        # Determine primary dimension
        dimension = self._determine_primary_dimension(issues)
        
        return JudgeEvaluation(
            verdict=verdict,
            reason=reason,
            dimension=dimension,
            score=score,
            issues=issues,
            recommendations=recommendations,
        )
    
    def execute(self, task: TaskEntity) -> WorkerResult:
        """
        Execute JUDGE evaluation.
        
        This is called by the supervisor to evaluate work.
        """
        # Get work to evaluate from task input
        input_data = task.input_data or {}
        work_output = input_data.get("work", {})
        acceptance_criteria = input_data.get("acceptance_criteria", [])
        
        # Perform evaluation
        evaluation = self.evaluate(task, work_output, acceptance_criteria)
        
        # Build result
        output = {
            "verdict": evaluation.verdict.value,
            "score": evaluation.score,
            "reason": evaluation.reason,
            "dimension": evaluation.dimension.value if evaluation.dimension else None,
            "issues": evaluation.issues,
            "recommendations": evaluation.recommendations,
        }
        
        # Return appropriate result based on verdict
        if evaluation.verdict == JudgeVerdict.APPROVED:
            return WorkerResult(
                success=True,
                output=output,
            )
        elif evaluation.verdict == JudgeVerdict.NEEDS_INFO:
            return WorkerResult(
                success=True,  # Not a failure, just needs clarification
                output=output,
            )
        else:  # REJECTED
            return WorkerResult(
                success=False,
                output=output,
                error=evaluation.reason,
            )
    
    def _check_acceptance_criteria(
        self,
        work: Dict[str, Any],
        criteria: List[str]
    ) -> List[str]:
        """Check if work meets acceptance criteria."""
        missing = []
        # Simplified check - would be more sophisticated in production
        for criterion in criteria:
            if criterion.lower() not in str(work).lower():
                missing.append(criterion)
        return missing
    
    def _check_interface_consistency(self, work: Dict[str, Any]) -> List[str]:
        """Check for interface consistency issues."""
        issues = []
        # Check for common interface issues
        if "api" in str(work).lower() and "docs" not in str(work).lower():
            issues.append("API changes without documentation")
        return issues
    
    def _check_contracts_compliance(self, work: Dict[str, Any]) -> List[str]:
        """Check compliance with contracts."""
        issues = []
        # Check for contract violations
        code = str(work.get("code", ""))
        if "TODO" in code or "FIXME" in code:
            issues.append("Code contains TODO/FIXME comments")
        return issues
    
    def _check_defects(self, work: Dict[str, Any]) -> List[str]:
        """Check for obvious defects."""
        issues = []
        # Check for missing files
        if "files" in work and not work["files"]:
            issues.append("No files produced")
        # Check for broken imports
        if "import error" in str(work).lower():
            issues.append("Import errors detected")
        return issues
    
    def _calculate_score(
        self,
        issues: List[str],
        criteria: Optional[List[str]]
    ) -> float:
        """Calculate quality score."""
        base_score = 1.0
        
        # Deduct for issues
        for _ in issues:
            base_score -= 0.15
        
        # Deduct for missing criteria
        if criteria:
            base_score -= 0.05 * len(criteria)
        
        return max(0.0, min(1.0, base_score))
    
    def _determine_primary_dimension(self, issues: List[str]) -> Optional[EvaluationDimension]:
        """Determine primary dimension from issues."""
        if not issues:
            return None
        
        # Simple heuristic - would be more sophisticated
        first_issue = issues[0].lower()
        if "acceptance" in first_issue:
            return EvaluationDimension.ACCEPTANCE_CRITERIA
        elif "interface" in first_issue or "api" in first_issue:
            return EvaluationDimension.INTERFACE_CONSISTENCY
        elif "contract" in first_issue or "todo" in first_issue:
            return EvaluationDimension.CONTRACTS_COMPLIANCE
        else:
            return EvaluationDimension.DEFECTS


def spawn_judge_evaluation(
    task: TaskEntity,
    work_output: Dict[str, Any],
    acceptance_criteria: Optional[List[str]] = None
) -> JudgeEvaluation:
    """
    Convenience function to spawn a JUDGE evaluation.
    
    Args:
        task: Original task
        work_output: Output from worker
        acceptance_criteria: Criteria to check
    
    Returns:
        JudgeEvaluation result
    """
    judge = JudgeWorker()
    
    # Set up task input
    task.input_data = {
        "work": work_output,
        "acceptance_criteria": acceptance_criteria or [],
        "original_description": task.description,
    }
    
    # Execute evaluation
    result = judge.process_task(task)
    
    # Extract evaluation from result
    output = result.payload
    
    return JudgeEvaluation(
        verdict=JudgeVerdict(output["verdict"]),
        reason=output["reason"],
        dimension=EvaluationDimension(output["dimension"]) if output.get("dimension") else None,
        score=output["score"],
        issues=output.get("issues", []),
        recommendations=output.get("recommendations", []),
    )


__all__ = [
    "JudgeWorker",
    "JudgeEvaluation",
    "JudgeVerdict",
    "EvaluationDimension",
    "spawn_judge_evaluation",
]
