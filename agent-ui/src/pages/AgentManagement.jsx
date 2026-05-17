import React, { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import { 
  Plus as PlusIcon, 
  Pencil as PencilIcon, 
  Trash2 as TrashIcon,
  CheckCircle as CheckCircleIcon,
  XCircle as XCircleIcon
} from 'lucide-react'

export default function AgentManagement() {
  const { tenant } = useAuth()
  const [agents, setAgents] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [editingAgent, setEditingAgent] = useState(null)
  const [formData, setFormData] = useState({
    name: '',
    type: 'ai',
    skills: [],
    config: {}
  })

  useEffect(() => {
    if (tenant) {
      fetchAgents()
    }
  }, [tenant])

  const fetchAgents = async () => {
    try {
      const res = await api.get(`/tenants/${tenant.id}/agents`)
      setAgents(res.data)
    } catch (error) {
      console.error('Failed to fetch agents:', error)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      if (editingAgent) {
        await api.put(`/tenants/${tenant.id}/agents/${editingAgent.id}`, formData)
      } else {
        await api.post(`/tenants/${tenant.id}/agents`, formData)
      }
      setShowModal(false)
      setFormData({ name: '', type: 'ai', skills: [], config: {} })
      setEditingAgent(null)
      fetchAgents()
    } catch (error) {
      console.error('Failed to save agent:', error)
    }
  }

  const handleDelete = async (agentId) => {
    if (window.confirm('Are you sure you want to delete this agent?')) {
      try {
        await api.delete(`/tenants/${tenant.id}/agents/${agentId}`)
        fetchAgents()
      } catch (error) {
        console.error('Failed to delete agent:', error)
      }
    }
  }

  const handleStatusChange = async (agentId, currentStatus) => {
    const newStatus = currentStatus === 'available' ? 'offline' : 'available'
    try {
      await api.patch(`/agents/${agentId}/status`, { status: newStatus })
      fetchAgents()
    } catch (error) {
      console.error('Failed to update status:', error)
    }
  }

  const availableSkills = ['sales', 'support', 'technical', 'billing', 'accounting']

  const getStatusColor = (status) => {
    switch (status) {
      case 'available': return 'text-green-600 bg-green-100'
      case 'busy': return 'text-red-600 bg-red-100'
      case 'online': return 'text-blue-600 bg-blue-100'
      case 'offline': return 'text-gray-400 bg-gray-100'
      case 'on_call': return 'text-yellow-600 bg-yellow-100'
      case 'paused': return 'text-purple-600 bg-purple-100'
      default: return 'text-gray-400 bg-gray-100'
    }
  }

  const getTypeColor = (type) => {
    switch (type) {
      case 'ai': return 'text-purple-600 bg-purple-100'
      case 'human': return 'text-green-600 bg-green-100'
      case 'hybrid': return 'text-blue-600 bg-blue-100'
      default: return 'text-gray-600 bg-gray-100'
    }
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Agent Management</h1>
          <p className="text-gray-600">Manage your AI and human agents</p>
        </div>
        <button
          onClick={() => { setShowModal(true); setEditingAgent(null) }}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Add Agent
        </button>
      </div>

      {/* Agent List */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Agent</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Skills</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">SIP Ext</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Calls</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {agents.map((agent) => (
              <tr key={agent.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <div className="h-10 w-10 flex-shrink-0 rounded-full bg-blue-100 flex items-center justify-center">
                      <span className="text-blue-600 font-medium text-sm">
                        {agent.display_name?.charAt(0) || agent.name.charAt(0)}
                      </span>
                    </div>
                    <div className="ml-4">
                      <div className="text-sm font-medium text-gray-900">{agent.display_name || agent.name}</div>
                      <div className="text-sm text-gray-500">{agent.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getTypeColor(agent.agent_type)}`}>
                    {agent.agent_type}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <button
                    onClick={() => handleStatusChange(agent.id, agent.status)}
                    className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full cursor-pointer hover:opacity-80 ${getStatusColor(agent.status)}`}
                  >
                    {agent.status === 'available' && <CheckCircleIcon className="h-4 w-4 mr-1" />}
                    {agent.status === 'busy' && <XCircleIcon className="h-4 w-4 mr-1" />}
                    {agent.status === 'online' && <CheckCircleIcon className="h-4 w-4 mr-1" />}
                    {agent.status}
                  </button>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex flex-wrap gap-1">
                    {agent.skills.map((skill) => (
                      <span key={skill} className="px-1 py-0.5 text-xs bg-gray-100 text-gray-600 rounded">
                        {skill}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {agent.sip_extension || '-'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {agent.total_calls}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => { setEditingAgent(agent); setFormData({ name: agent.name, type: agent.agent_type, skills: agent.skills, config: agent.config }); setShowModal(true) }}
                    className="text-indigo-600 hover:text-indigo-900 mr-3"
                  >
                    <PencilIcon className="h-5 w-5" />
                  </button>
                  <button
                    onClick={() => handleDelete(agent.id)}
                    className="text-red-600 hover:text-red-900"
                  >
                    <TrashIcon className="h-5 w-5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Add/Edit Agent Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-6">
            <h2 className="text-lg font-semibold mb-4">
              {editingAgent ? 'Edit Agent' : 'Add New Agent'}
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Type</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                >
                  <option value="ai">AI Agent</option>
                  <option value="human">Human Agent</option>
                  <option value="hybrid">Hybrid Agent</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Skills</label>
                <div className="flex flex-wrap gap-2">
                  {availableSkills.map((skill) => (
                    <button
                      key={skill}
                      type="button"
                      onClick={() =>
                        setFormData({
                          ...formData,
                          skills: formData.skills.includes(skill)
                            ? formData.skills.filter((s) => s !== skill)
                            : [...formData.skills, skill],
                        })
                      }
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        formData.skills.includes(skill)
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                    >
                      {skill}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex justify-end space-x-3 mt-6">
                <button
                  type="button"
                  onClick={() => { setShowModal(false); setFormData({ name: '', type: 'ai', skills: [], config: {} }) }}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
                >
                  {editingAgent ? 'Update Agent' : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
