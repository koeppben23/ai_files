from typing import Any, Dict, Optional
from .schema import SessionState, CommitFlags, LoadedRulebooks


class TransitionType:
    SET_PHASE = "set_phase"
    SET_PROFILE = "set_profile"
    LOAD_RULEBOOK = "load_rulebook"
    COMMIT_PERSISTENCE = "commit_persistence"
    SET_FILE_STATUS = "set_file_status"
    SET_IDENTITY = "set_identity"


def apply_transition(state: SessionState, transition: Dict[str, Any]) -> SessionState:
    transition_type = transition.get("type")
    
    if transition_type == TransitionType.SET_PHASE:
        state.phase_token = transition.get("phase", state.phase_token)
    
    elif transition_type == TransitionType.SET_PROFILE:
        state.profile = transition.get("profile")
    
    elif transition_type == TransitionType.LOAD_RULEBOOK:
        rulebook_type = transition.get("rulebook_type", "core")
        rulebook_name = transition.get("rulebook_name")
        if rulebook_name:
            if rulebook_type == "core":
                if rulebook_name not in state.LoadedRulebooks.core:
                    state.LoadedRulebooks.core.append(rulebook_name)
            elif rulebook_type == "domain":
                if rulebook_name not in state.LoadedRulebooks.domain:
                    state.LoadedRulebooks.domain.append(rulebook_name)
            elif rulebook_type == "local":
                if rulebook_name not in state.LoadedRulebooks.local:
                    state.LoadedRulebooks.local.append(rulebook_name)
    
    elif transition_type == TransitionType.COMMIT_PERSISTENCE:
        state.CommitFlags.PersistenceCommitted = True
        state.CommitFlags.WorkspaceReadyGateCommitted = True
        state.CommitFlags.WorkspaceArtifactsCommitted = True
        state.CommitFlags.PointerVerified = True
    
    elif transition_type == TransitionType.SET_FILE_STATUS:
        file_key = transition.get("file_key")
        file_status = transition.get("file_status")
        if file_key and file_status:
            state.Files[file_key] = file_status
    
    elif transition_type == TransitionType.SET_IDENTITY:
        repo_fingerprint = transition.get("repo_fingerprint")
        repo_name = transition.get("repo_name")
        if repo_fingerprint and repo_name:
            state.IdentityMap[repo_fingerprint] = repo_name
    
    return state


def compute_next_action(state: SessionState) -> Optional[str]:
    if not state.CommitFlags.WorkspaceArtifactsCommitted:
        return "backfill_artifacts"
    
    if not state.CommitFlags.PointerVerified:
        return "verify_pointer"
    
    if not state.CommitFlags.PersistenceCommitted:
        return "commit_persistence"
    
    if state.phase_token in ["0-None", "1.1-Bootstrap"]:
        return "advance_to_1.3"
    
    return None
