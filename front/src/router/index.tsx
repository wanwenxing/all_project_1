import AuthLayout from '@/layouts/AuthLayout'
import BasicLayout from '@/layouts/BasicLayout'
import About from '@/pages/About'
import EvalCasesPage from '@/pages/Eval/Cases'
import EvalRunsPage from '@/pages/Eval/Runs'
import Home from '@/pages/Home'
import Knowledge from '@/pages/Knowledge'
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import { createBrowserRouter } from 'react-router-dom'

const router = createBrowserRouter([
  {
    path: '/',
    element: <BasicLayout />,
    children: [
      {
        index: true,
        element: <Home />,
      },
      {
        path: 'knowledge',
        element: <Knowledge />,
      },
      {
        path: 'evals/cases',
        element: <EvalCasesPage />,
      },
      {
        path: 'evals/runs',
        element: <EvalRunsPage />,
      },
      {
        path: 'about',
        element: <About />,
      },
    ],
  },
  {
    path: '/',
    element: <AuthLayout />,
    children: [
      {
        path: 'login',
        element: <Login />,
      },
      {
        path: 'register',
        element: <Register />,
      },
    ],
  },
])

export default router
