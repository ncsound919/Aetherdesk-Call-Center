import React from 'react';

const ToastNotification = ({ message, type = 'info', onClose }) => {
  return (
    <div className={`toast toast-${type}`}>
      {message}
      <button onClick={onClose}>X</button>
    </div>
  );
};
export default ToastNotification;
