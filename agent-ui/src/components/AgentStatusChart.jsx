import React from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const data = [
  { name: 'Online', count: 8, color: '#3b82f6' },
  { name: 'Available', count: 8, color: '#10b981' },
  { name: 'Busy', count: 2, color: '#ef4444' },
  { name: 'On Call', count: 6, color: '#f59e0b' },
  { name: 'Paused', count: 1, color: '#8b5cf6' },
  { name: 'Offline', count: 9, color: '#94a3b8' },
]

export default function AgentStatusChart() {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-sm font-medium text-gray-700 mb-4">Agent Status Overview</h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="count" fill="#3b82f6">
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}