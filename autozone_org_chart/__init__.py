from . import models


def post_init_hook(env):
    """Seed hr.department.sequence from creation order.

    Departments were entered in the order FM-HR-36 reads, so their ids already
    carry that arrangement; the default sequence would throw it away and fall
    back to the id tiebreaker only. Spacing by ten leaves room to drop a
    department between two others without renumbering the rest.
    """
    env["hr.department"].with_context(active_test=False).search([])._seed_sequence()
