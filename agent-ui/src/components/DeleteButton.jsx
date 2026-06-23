import React, { useState, useCallback } from 'react';
import ConfirmationModal from './ConfirmationModal';

const DeleteButton = ({
  action,
  itemId,
  label = 'Delete',
  title = 'Confirm Deletion',
}) => {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState(null);

  const handleConfirm = useCallback(async () => {
    if (typeof action !== 'function') return;
    setIsDeleting(true);
    setError(null);
    try {
      await action(itemId);
      // Only close the modal after a successful deletion.
      setIsConfirming(false);
    } catch (err) {
      // Keep the modal open so the user can see the error and retry or cancel.
      setError(err);
    } finally {
      setIsDeleting(false);
    }
  }, [action, itemId]);

  const handleCancel = useCallback(() => {
    // Prevent closing while a deletion is in flight.
    if (isDeleting) return;
    setIsConfirming(false);
  }, [isDeleting]);

  return (
    <>
      <button
        onClick={() => setIsConfirming(true)}
        disabled={isDeleting}
      >
        {label}
      </button>
      <ConfirmationModal
        isOpen={isConfirming}
        title={title}
        message={
          error
            ? `Deletion failed: ${error.message || 'Unknown error'}. Please try again.`
            : 'Are you sure you want to delete this item? This action cannot be undone.'
        }
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  );
};

export default DeleteButton;
