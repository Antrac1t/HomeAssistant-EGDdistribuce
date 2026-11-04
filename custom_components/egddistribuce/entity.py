import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import EGDDistribuceCoordinator


def suggest_entity_id(platform: str, key: str, entry: ConfigEntry) -> str:
    """Suggest an ID for new entities; the registry retains existing IDs."""
    name = slugify(entry.title)
    # Default titles start with "EGD HDO", which would repeat the fixed prefix.
    name = re.sub(r"^egd_(?:hdo_|(?!hdo$))", "", name) or name
    return f"{platform}.egd_{key}_{name}"


def format_slot(slot: dict, separator: str = "-") -> str:
    """Format an HDO slot {'od', 'do'} for display."""
    start = slot.get("od", "").replace(":00", "")
    end = slot.get("do", "").replace(":00", "")
    return f"{start}{separator}{end}"


def format_slots(slots: list) -> str:
    """Format HDO slots as one comma separated string."""
    return ", ".join(format_slot(slot) for slot in slots) if slots else "Žádné"


def device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device that groups all entities of one config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="EGD Distribuce",
        model="HDO",
        entry_type=DeviceEntryType.SERVICE,
    )


class EGDBaseEntity(CoordinatorEntity[EGDDistribuceCoordinator]):
    """Base entity for EGD integration.

    Subclasses set ``_platform`` and ``_attr_translation_key``; the key also
    forms the unique ID and the suggested entity ID.
    """

    _attr_has_entity_name = True
    _platform: str

    def __init__(self, coordinator: EGDDistribuceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        key = self._attr_translation_key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self.entity_id = suggest_entity_id(self._platform, key, entry)
        self._attr_device_info = device_info(entry)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.data is not None
