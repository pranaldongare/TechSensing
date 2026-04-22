import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@/lib/theme-context';
import { Toaster } from '@/components/ui/toaster';
import TechSensing from '@/pages/TechSensing';
import CompanyAnalysisPage from '@/pages/CompanyAnalysisPage';
import KeyCompaniesPage from '@/pages/KeyCompaniesPage';
import ModelReleasesPage from '@/pages/ModelReleasesPage';
import AILeaderboardPage from '@/pages/AILeaderboardPage';
import SettingsPage from '@/pages/SettingsPage';

function App() {
  return (
    <ThemeProvider>
      <Router>
        <Routes>
          <Route path="/" element={<TechSensing />} />
          <Route path="/company-analysis" element={<CompanyAnalysisPage />} />
          <Route path="/key-companies" element={<KeyCompaniesPage />} />
          <Route path="/model-releases" element={<ModelReleasesPage />} />
          <Route path="/ai-leaderboard" element={<AILeaderboardPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster />
      </Router>
    </ThemeProvider>
  );
}

export default App;
