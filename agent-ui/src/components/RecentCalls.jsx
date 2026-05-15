import React from 'react'
import { PhoneIncoming, PhoneOutgoing, ArrowRight } from 'lucide-react'

const calls = [
  { id: 1, direction: 'inbound', from: '+1 (555) 123-4567', to: '+1 (800) 555-0000', agent: 'John Smith', duration: '5:32', cost: '$0.45', status: 'completed', intent: 'support' },
  { id: 2, direction: 'outbound', from: '+1 (800) 555-0000', to: '+1 (555) 987-6543', agent: 'Jane Doe', duration: '12:15', cost: '$0.98', status: 'completed', intent: 'sales' },
  { id: 3, direction: 'inbound', from: '+1 (555) 456-7890', to: '+1 (800) 555-0000', agent: '-', duration: '0:00', cost: '$0.00', status: 'missed', intent: 'billing' },
]

export default function RecentCalls() {
  const getDirectionIcon = (direction) => {
    if (direction === 'inbound') {
      return <PhoneIncoming className="h-4 w-4 text-green-500" />
    }
    return <PhoneOutgoing className="h-4 w-4 text-blue-500" />
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-100'
      case 'missed': return 'text-red-600 bg-red-100'
      default: return 'text-gray-400 bg-gray-100'
    }
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-sm font-medium text-gray-700">Recent Calls</h3>
      </div>
      <ul className="divide-y divide-gray-200">
        {calls.map((call) => (
          <li key={call.id} className="px-6 py-4 hover:bg-gray-50 transition-colors cursor-pointer group">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className={`p-2 rounded-lg ${call.direction === 'inbound' ? 'bg-green-50' : 'bg-blue-50'}`}>
                  {getDirectionIcon(call.direction)}
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900">{call.from}</p>
                  <p className="text-sm text-gray-500">
                    {call.direction === 'inbound' ? '→' : '←'} {call.to}
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-4">
                <span className={`px-2 py-0.5 text-xs rounded-full ${getStatusColor(call.status)}`}>
                  {call.status}
                </span>
                <span className="text-sm text-gray-500">{call.duration}</span>
                <span className="text-sm text-gray-500">{call.cost}</span>
                <ArrowRight className="h-5 w-5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}