from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EGDDistribuceCoordinator


class EGDBaseEntity(CoordinatorEntity[EGDDistribuceCoordinator]):
    """Base entity for EGD integration."""

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.data is not None
