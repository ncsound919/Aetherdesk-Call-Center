import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { toast } from 'sonner'

export default function LeadImportPage() {
  const { tenant } = useAuth()
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const navigate = useNavigate()

  const handleUpload = async () => {
    if (!file || !tenant) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('tenant_id', tenant.id)
      await api.post('/leads/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      toast.success('Leads imported successfully')
      navigate('/leads')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900 mb-4">Import Leads</h1>
      <p className="text-gray-600 mb-6">Upload a CSV file with columns: name, phone, email</p>
      <div className="max-w-lg space-y-4">
        <input
          type="file"
          accept=".csv"
          onChange={(e) => setFile(e.target.files[0])}
          className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
        />
        <div className="flex gap-2">
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
          >
            {uploading ? 'Uploading...' : 'Import'}
          </button>
          <button
            onClick={() => navigate('/leads')}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
