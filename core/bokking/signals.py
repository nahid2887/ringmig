"""
Django signals for ListenerAvailability model.
DISABLED: Broadcasting is now handled manually in ViewSet after each save.
This prevents race conditions with nested time_slots creation.
"""
# Signals disabled - using manual broadcast calls in ViewSet instead
