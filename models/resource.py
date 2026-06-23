from pydantic import BaseModel, Field


class Resource(BaseModel):
    """A versioned data resource with optimistic locking support."""

    id: str
    data: dict
    version: int = Field(default=0, ge=0)

    def update(self, new_data: dict, expected_version: int | None = None) -> "Resource":
        """
        Merge *new_data* into the resource and bump the version.

        Parameters
        ----------
        new_data:
            Key/value pairs to merge into ``self.data``.
        expected_version:
            If supplied, the caller's copy of ``self.version`` at read time.
            A ``ValueError`` is raised when it does not match
            ``self.version``, signalling that another writer has modified
            the resource in the meantime (optimistic lock failure).

        Raises
        ------
        ValueError
            When ``expected_version`` is not ``None`` and differs from the
            current ``self.version``.

        Returns
        -------
        Resource
            ``self``, for call-chaining convenience.
        """
        if expected_version is not None and self.version != expected_version:
            raise ValueError(
                f"Version conflict on resource {self.id!r}: "
                f"expected version {expected_version}, "
                f"but current version is {self.version}"
            )
        # Assign a new dict to avoid mutating a shared reference in-place.
        self.data = {**self.data, **new_data}
        self.version += 1
        return self
