import React from 'react'

export default function Sidebar({ open, onClose }) {
  const menuItems = [
    { icon: '📊', label: 'Dashboard', path: '/' },
    { icon: '👥', label: 'Agents', path: '/agents' },
    { icon: '📞', label: 'Call Logs', path: '/calls' },
    { icon: '🎙️', label: 'Voice Cloning', path: '/voice-cloning' },
    { icon: '💳', label: 'Billing', path: '/billing' },
    { icon: '📋', label: 'Leads', path: '/leads' },
    { icon: '📝', label: 'Scripts', path: '/scripts' },
    { icon: '⚙️', label: 'Settings', path: '/settings' },
  ]

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`fixed lg:static inset-y-0 left-0 w-64 bg-white border-r border-gray-200 transform ${
          open ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0 transition-transform duration-200 ease-in-out z-50`}
      >
        <div className="h-16 flex items-center justify-center border-b border-gray-200">
          <span className="text-xl font-bold text-blue-600">AetherDesk</span>
        </div>
        <nav className="mt-4 px-3">
          {menuItems.map((item) => (
            <a
              key={item.path}
              href={item.path}
              className="flex items-center px-4 py-3 text-sm font-medium rounded-lg text-gray-700 hover:bg-blue-50 hover:text-blue-600 mb-1 transition-colors"
            >
              <span className="mr-3">{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="absolute bottom-0 w-full p-4 border-t border-gray-200">
          <div className="flex items-center">
            <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
              <span className="text-blue-600 text-sm font-medium">A</span>
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-700">Admin</p>
              <p className="text-xs text-gray-500">admin@aetherdesk.com</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}