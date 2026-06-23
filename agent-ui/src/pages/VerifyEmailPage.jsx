import React, { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { toast } from 'sonner'
import api from '../services/api'

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState('verifying')
  const token = searchParams.get('token')

  useEffect(() => {
    if (!token) {
      setStatus('missing')
      return
    }
    api.post('/auth/verify-email', { token })
      .then(() => {
        setStatus('success')
        toast.success('Email verified successfully')
      })
      .catch(() => {
        setStatus('error')
        toast.error('Email verification failed')
      })
  }, [token])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full text-center space-y-4">
        {status === 'verifying' && <p className="text-gray-600">Verifying your email...</p>}
        {status === 'success' && (
          <>
            <p className="text-green-600 font-semibold">Email verified!</p>
            <Link to="/login" className="text-blue-600 hover:underline">Go to login</Link>
          </>
        )}
        {status === 'error' && (
          <>
            <p className="text-red-600">Verification failed or token expired.</p>
            <Link to="/login" className="text-blue-600 hover:underline">Go to login</Link>
          </>
        )}
        {status === 'missing' && (
          <p className="text-red-600">Missing verification token.</p>
        )}
      </div>
    </div>
  )
}
