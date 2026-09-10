from . import models


def post_init_hook(env):
    """Create the 'เบิกใช้วัสดุ' operation type for every existing warehouse."""
    env["stock.warehouse"].search([])._create_consumption_picking_type()
