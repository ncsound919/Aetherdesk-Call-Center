import React from 'react'

export default function StatCard({ title, value, icon, color, bgColor }) {
  return (
    <div className={`bg-white rounded-lg shadow p-6 border-l-4 ${bgColor.replace('50', '200')}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-600">{title}</p>
          <p className="text-2xl font-semibold text-gray-900 mt-1">{value}</p>
        </div>
        <div className={`p-3 rounded-lg ${bgColor}`}>
          {icon}
        </div>
      </div>
    </div>
  )
}