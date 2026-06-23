import React, { useState } from 'react';
import ConfirmationModal from './ConfirmationModal';

const DeleteButton = ({ action, itemId }) => {
  const [isConfirming, setIsConfirming] = useState(false);
  const handleConfirm = () => {
    action(itemId);
    setIsConfirming(false);
  };
  const handleCancel = () => setIsConfirming(false);

  return (
    <>
      <button onClick={() => setIsConfirming(true)}>Delete</button>
      <ConfirmationModal
        isOpen={isConfirming}
        title="Confirm Deletion"
        message="Are you sure you want to delete this item? This action cannot be undone."
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  );
};
export default DeleteButton;
