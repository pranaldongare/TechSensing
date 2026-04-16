import React from 'react';
import { Building2 } from 'lucide-react';
import AppNavbar from '@/components/AppNavbar';
import CompanyAnalysisView from '@/components/CompanyAnalysisView';

const CompanyAnalysisPage: React.FC = () => {
  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 flex flex-col p-6 gap-4 overflow-hidden min-h-0">
        <div className="flex items-center gap-3 shrink-0">
          <Building2 className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-2xl font-bold leading-tight">Company Analysis</h2>
            <p className="text-xs text-muted-foreground">
              Compare how companies engage with any set of technologies or areas.
            </p>
          </div>
        </div>
        <div className="flex-1 overflow-auto min-h-0">
          <CompanyAnalysisView standalone />
        </div>
      </div>
    </div>
  );
};

export default CompanyAnalysisPage;
