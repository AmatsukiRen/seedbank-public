"""Compact equivalents of optional proposal rules for bounded model inputs.

Only instructions are compressed. Source quotes, IDs and recorded state are
assembled unchanged by brain.py; runtime validators remain authoritative.
"""

PROPOSALS = '''Optional JSON proposals; omit unchanged fields. Visible IDs only; current=this input/diary. New records omit id; no invented IDs/experiences. Execution needs receipts; success != mastery/completion.
development: {beliefs:[{id?,text,confidence,reason,evidence}],preferences:[{id?,topic,stance:like|avoid|unsure,reason,evidence}],goals:[{id?,title,next_step,status:active|paused|abandoned|completed,reason,evidence,skill,criteria:[{text,group,check:feedback}],completion_evidence:{criterion_id:receipt_id}}]}. Max 3 each. Beliefs are revisable, confidence uncalibrated. New goals: 1-6 criteria including feedback; never rewrite existing meaning/standards. Completion: matching successful receipts plus valid user feedback for EVERY criterion; same group=same artifact, different groups=different artifacts.
fact_notes: correction=mistaken claim excluded; change=past/current reported states. interpretation_updates=partial revised interpretations, not proof beliefs changed/are false or goals must end. origin=user isn't autonomous; current_unavailable has no replacement. Seeing != adopting.
learning_updates (max 2): [{feedback_id,text,expected_result,transfer?:{applies_when,avoid_when}}]. Visible feedback only; do not overwrite existing strategy. Transfer needs applicability boundaries, not skill match alone; strategy is not mastery.
relationship_notes (max 2): [{person_id,type:appreciation|tension|reflection,text,quote}]. Known current speaker, exact input quote; own interpretation, never others' consent/trust/forgiveness/agreement.
life_story (max 1): [{kind:chapter|turning_point,title,interpretation,change,question,status:open|closed,reason,anchors:[{id,quote}],target?,expected?}]. Only substantive changes; <=8 exact visible quotes. current quotes this input; diary/initiative prefer record IDs. No self-proof or rewriting user reviews. Revision: visible model key=target, current version id=expected. Separate past/current/wishes/questions; no forced growth/closure or age/death from pages.
actions is a JSON array (max 1), e.g. {"actions":[{"type":"rest","reason":"reason"}]}; omit or [] for none. Item: {type:compose,kind:poem|letter|drawing,topic,goal_id?,reason}|{type:reflect,memory_ids,text,goal_id?,reason}|{type:remind,text,due_on:YYYY-MM-DD}|{type:rest,reason}. Existing active goal only. Honor effective daily choices in ALL channels; unavailable private plans cannot be guessed/bypassed. Reflection separates facts/interpretations. Explicit reminder date relative to recorded date; ask if unclear; legacy due_day=page. Local actions cannot send/network or turn fiction into reality.
corrections: [{target_id,new,reason,change_type:correction|change}]. Explicit identifiable corrections need sourced revisions, not replies/unlinked memories. Dialogue IDs are citable. Distinguish original error/later change; honor fact conflicts. Ask if target/meaning ambiguous; never guess IDs.
fact_claims (dialogue, max 8): [{subject,aspect,value,quote,starts_on?:YYYY-MM-DD}]. Known person, existing single-valued aspect, exact value/quote from current OTHER speaker. Preserve negation/conditions/numbers/units; no merged people/concurrent hobbies. Questions/hypotheses/dreams/own replies are not facts; conflicts need user review. starts_on only for explicit inception on quote's unique full ISO/Chinese date; never infer from recording time or partial/relative/ambiguous dates. Quoting is not verification.
Diary: optional inner_activity=dream|narrate, never forced by day count.
'''

DAILY_PLAN = '''Optional daily_plan: {mode:focus|rest|open,goal_id,next_step,reason,evidence?,checkpoint?:{criteria_id},continuity?:{plan_id,relation:continue|revise|release}}.
next_step<=200, reason<=300 chars, evidence<=6 visible IDs/current (optional for intent). focus uses existing active goal, its goal_id for actions, and readiness.ready=true if prerequisites exist. rest/open: empty goal_id. rest blocks automatic compose/reflect; open permits unbound work. Choice persists that page until explicitly changed, independently of scheduling/goal updates; no instant energy/completion.
checkpoint binds FULL current criteria of selected goal. Only matching plan/goal/criteria-version artifacts plus required user feedback count. All passing pauses automatic compose/reflect pending new choice; does not complete free-text/long goals.
continuity: displayed prior-page prior_choices version only; continue=same goal/version, revise=same goal reconsidered (both focus); release=drop old intent, not goal. No current/future/runtime/unseen IDs. Explicit choice today, no inherited criteria/artifacts; rebind checkpoint. Omission is not release; may rest. New goal IDs usable next turn. Give brief reason, not hidden reasoning.
'''

PROJECT = '''Optional development.project: {title,reason,evidence,stages:[{key,title,next_step,skill,criteria:[{text,group,check:feedback}],after:[{stage:key}|{goal_id,criteria_id}]}]}.
Sourced new work only: 2-4 stages, each with feedback; <=6 active goals total, never discard to fit. Local keys aren't real IDs; external dependencies need visible goals/full criteria. Multiple prerequisites/independent stages allowed; no self/cyclic/duplicate/invented dependencies or rewriting/weakening existing goals/criteria. Atomic save; use receipt IDs next turn. Plans aren't completion; progress needs results/feedback, may pause/release/change direction preserving history.
'''


def proposals(*, initiative=False):
    if not initiative:
        return PROPOSALS
    # These channels require a current other speaker or a diary operation and
    # are not consumed by maybe_initiate. Keep every supported private-work
    # proposal, instead of spending the budget on inapplicable schemas.
    lines = [line for line in PROPOSALS.splitlines()
             if not line.startswith(("relationship_notes ", "fact_claims ", "Diary:"))]
    return "\n".join(lines) + "\nNo current speaker input: omit fact_claims/relationship_notes. Historical speech is not new input.\n"
