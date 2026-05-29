import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useSocket } from '../context/SocketContext'
import api from '../services/api'
import StatCard from '../components/StatCard'
import AgentStatusChart from '../components/AgentStatusChart'
import CallVolumeChart from '../components/CallVolumeChart'
import RecentCalls from '../components/RecentCalls'
import {
  PhoneIncoming as PhoneIncomingIcon,
  PhoneOutgoing as PhoneOutgoingIcon,
  Clock as ClockIcon,
  Users as UsersIcon,
  CheckCircle,
  AlertCircle
} from 'lucide-react'

export default function Dashboard() {
  const { tenant } = useAuth()
  const [stats, setStats] = useState({
    activeCalls: 0,
    totalCallsToday: 0,
    avgCallDuration: '0:00',
    availableAgents: 0,
    totalAgents: 0,
    missedCalls: 0,
  })
  const [recentCalls, setRecentCalls] = useState([])
  const socket = useSocket()

  const fetchStats = useCallback(async () => {
    if (!tenant) return
    try {
      const today = new Date().toISOString().split('T')[0]
      const res = await api.get(
        `/usage?tenant_id=${tenant.id}&period_start=${today}T00:00:00&period_end=${new Date().toISOString()}`
      )
      const data = res.data
      setStats({
        activeCalls: data.active_calls || 0,
        totalCallsToday: data.total_calls || 0,
        avgCallDuration: formatDuration(data.avg_call_duration || 0),
        availableAgents: data.active_agents || 0,
        totalAgents: data.total_agents || 0,
        missedCalls: 0,
      })
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }, [tenant])

  const fetchRecentCalls = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await api.get(`/calls?tenant_id=${tenant.id}&status=completed`)
      setRecentCalls(Array.isArray(res.data) ? res.data.slice(0, 10) : [])
    } catch (error) {
      console.error('Failed to fetch calls:', error)
      setRecentCalls([])
    }
  }, [tenant])

  function formatDuration(minutes) {
    const hrs = Math.floor(minutes / 60)
    const mins = Math.round(minutes % 60)
    if (hrs > 0) return `${hrs}h ${mins}m`
    return `${mins}m`
  }

  // Initial load
  useEffect(() => {
    fetchStats()
    fetchRecentCalls()
  }, [fetchStats, fetchRecentCalls])

  // Listen for real-time WebSocket updates
  useEffect(() => {
    if (!socket?.tenantSocket) return

    const handleCallStatus = (event) => {
      const data = event.detail
      if (data && data.type === 'call:status') {
        // Refresh stats when call status changes
        fetchStats()
        fetchRecentCalls()
      }
    }

    // Also listen for call assignments
    const handleCallAssigned = (event) => {
      fetchStats()
    }

    window.addEventListener('call:status', handleCallStatus)
    window.addEventListener('call:assigned', handleCallAssigned)

    return () => {
      window.removeEventListener('call:status', handleCallStatus)
      window.removeEventListener('call:assigned', handleCallAssigned)
    }
  }, [socket, fetchStats, fetchRecentCalls])

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="text-gray-600">Overview of your call center operations</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4 mb-6">
        <StatCard
          title="Active Calls"
          value={stats.activeCalls}
          icon={<PhoneIncomingIcon className="h-6 w-6" />}
          color="text-green-600"
          bgColor="bg-green-50"
        />
        <StatCard
          title="Total Calls Today"
          value={stats.totalCallsToday}
          icon={<PhoneOutgoingIcon className="h-6 w-6" />}
          color="text-blue-600"
          bgColor="bg-blue-50"
        />
        <StatCard
          title="Avg Call Duration"
          value={stats.avgCallDuration}
          icon={<ClockIcon className="h-6 w-6" />}
          color="text-purple-600"
          bgColor="bg-purple-50"
        />
        <StatCard
          title="Available Agents"
          value={`${stats.availableAgents} / ${stats.totalAgents}`}
          icon={<UsersIcon className="h-6 w-6" />}
          color="text-indigo-600"
          bgColor="bg-indigo-50"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 mb-6">
        <AgentStatusChart
          agents={
            stats.totalAgents > 0
              ? [
                  { name: 'Available', value: stats.availableAgents },
                  { name: 'Active', value: stats.activeCalls },
                ]
              : []
          }
        />
        <CallVolumeChart calls={recentCalls} />
      </div>

      {/* Recent Calls */}
      <RecentCalls calls={recentCalls} />
    </div>
  )
}