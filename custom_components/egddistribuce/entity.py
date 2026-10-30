import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .coordinator import EGDDistribuceCoordinator


def suggest_entity_id(platform: str, key: str, entry: ConfigEntry) -> str:
    """Suggest an ID for new entities; the registry retains existing IDs."""
    name = slugify(entry.title)
    # Default titles start with "EGD HDO", which would repeat the fixed prefix.
    name = re.sub(r"^egd_(?:hdo_|(?!hdo$))", "", name) or name
    return f"{platform}.egd_{key}_{name}"


class EGDBaseEntity(CoordinatorEntity[EGDDistribuceCoordinator]):
    """Base entity for EGD integration."""

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.data is not None
