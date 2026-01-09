"""
State machine for managing user registration workflow.
Uses the 'transitions' library for runtime state verification.
This is an additional layer that tracks registration progress without
modifying the core registration logic.
"""

from transitions import Machine
from datetime import datetime
import logging

# Configure logging for audit trail
logger = logging.getLogger('registration_state_machine')


class RegistrationStateMachine:
    """
    State machine for managing user registration workflow.
    
    States:
    - initial: Starting state, no data submitted
    - data_submitted: Registration form data has been submitted
    - django_validated: Django form validation passed
    - marshmallow_validated: Marshmallow validation passed
    - user_created: User account created in database
    - email_sent: Verification email has been sent
    - email_verified: User has verified their email
    - registration_complete: Full registration process completed
    - failed: Registration failed at some step
    
    Transitions ensure users follow the correct registration flow.
    """
    
    # Define all possible states
    states = [
        'initial',
        'data_submitted',
        'django_validated',
        'marshmallow_validated',
        'user_created',
        'email_sent',
        'email_verified',
        'registration_complete',
        'failed'
    ]
    
    def __init__(self, username=None):
        """Initialize the state machine for a registration attempt."""
        self.username = username
        self.error_message = None
        self.created_at = datetime.now()
        self.state_history = []
        self.validation_passed = False
        self.token_valid = False
        
        # Initialize the state machine
        self.machine = Machine(
            model=self,
            states=RegistrationStateMachine.states,
            initial='initial',
            auto_transitions=False,  # Disable automatic transitions for security
            send_event=True  # Pass event data to callbacks
        )
        
        # Define allowed transitions with callbacks
        self._setup_transitions()
    
    def _setup_transitions(self):
        """Configure all allowed state transitions with guards and callbacks."""
        
        # initial -> data_submitted
        self.machine.add_transition(
            trigger='submit_data',
            source='initial',
            dest='data_submitted',
            before='_log_transition',
            after='_record_state_change'
        )
        
        # data_submitted -> django_validated
        self.machine.add_transition(
            trigger='django_validate',
            source='data_submitted',
            dest='django_validated',
            before='_log_transition',
            after='_record_state_change'
        )
        
        # django_validated -> marshmallow_validated
        self.machine.add_transition(
            trigger='marshmallow_validate',
            source='django_validated',
            dest='marshmallow_validated',
            conditions=['_has_valid_data'],
            before='_log_transition',
            after='_record_state_change'
        )
        
        # marshmallow_validated -> user_created
        self.machine.add_transition(
            trigger='create_user',
            source='marshmallow_validated',
            dest='user_created',
            before='_log_transition',
            after='_record_state_change'
        )
        
        # user_created -> email_sent
        self.machine.add_transition(
            trigger='send_verification_email',
            source='user_created',
            dest='email_sent',
            before='_log_transition',
            after='_record_state_change'
        )
        
        # email_sent -> email_verified
        self.machine.add_transition(
            trigger='verify_email',
            source='email_sent',
            dest='email_verified',
            conditions=['_has_valid_token'],
            before='_log_transition',
            after='_record_state_change'
        )
        
        # email_verified -> registration_complete
        self.machine.add_transition(
            trigger='complete_registration',
            source='email_verified',
            dest='registration_complete',
            before='_log_transition',
            after='_record_state_change'
        )
        
        # Any state can transition to failed
        self.machine.add_transition(
            trigger='fail',
            source='*',
            dest='failed',
            before='_log_failure',
            after='_record_state_change'
        )
        
        # Allow retry from failed state
        self.machine.add_transition(
            trigger='retry',
            source='failed',
            dest='initial',
            before='_log_transition',
            after='_record_state_change'
        )
    
    # Guard conditions
    def _has_valid_data(self, event):
        """Guard: Check if validation data is present."""
        return getattr(self, 'validation_passed', False)
    
    def _has_valid_token(self, event):
        """Guard: Check if verification token is valid."""
        return getattr(self, 'token_valid', False)
    
    # Callbacks
    def _log_transition(self, event):
        """Log state transition for audit trail."""
        logger.info(
            f"Registration [{self.username}]: "
            f"Transition '{event.event.name}' from '{event.transition.source}' to '{event.transition.dest}'"
        )
    
    def _log_failure(self, event):
        """Log failure with error details."""
        logger.warning(
            f"Registration [{self.username}]: "
            f"FAILED from state '{event.transition.source}'. "
            f"Error: {self.error_message}"
        )
    
    def _record_state_change(self, event):
        """Record state change in history."""
        self.state_history.append({
            'from_state': event.transition.source,
            'to_state': event.transition.dest,
            'trigger': event.event.name,
            'timestamp': datetime.now().isoformat()
        })
    
    # Public methods for registration flow
    def set_validation_result(self, passed, errors=None):
        """Set the result of Marshmallow validation."""
        self.validation_passed = passed
        if not passed:
            self.error_message = errors
    
    def set_token_validation(self, valid):
        """Set the result of token validation."""
        self.token_valid = valid
    
    def get_state_history(self):
        """Return the complete state history for debugging/audit."""
        return self.state_history
    
    def can_proceed(self):
        """Check if registration can proceed based on current state."""
        return self.state not in ['failed', 'registration_complete']


class RegistrationStateManager:
    """
    Manager class to handle multiple registration state machines.
    Stores state machines in session for persistence across requests.
    """
    
    SESSION_KEY = 'registration_state'
    
    @classmethod
    def get_or_create(cls, request, username=None):
        """Get existing state machine from session or create new one."""
        state_data = request.session.get(cls.SESSION_KEY)
        
        if state_data and state_data.get('username') == username:
            # Restore existing state machine
            machine = RegistrationStateMachine(username)
            machine.state = state_data.get('state', 'initial')
            machine.state_history = state_data.get('history', [])
            return machine
        
        # Create new state machine
        return RegistrationStateMachine(username)
    
    @classmethod
    def save(cls, request, machine):
        """Save state machine to session."""
        request.session[cls.SESSION_KEY] = {
            'username': machine.username,
            'state': machine.state,
            'history': machine.state_history
        }
    
    @classmethod
    def clear(cls, request):
        """Clear state machine from session."""
        if cls.SESSION_KEY in request.session:
            del request.session[cls.SESSION_KEY]
