import React from 'react';
import { Briefcase } from 'lucide-react';
import AppNavbar from '@/components/AppNavbar';
import KeyCompaniesView from '@/components/KeyCompaniesView';

const KeyCompaniesPage: React.FC = () => {
  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 flex flex-col p-6 gap-4 overflow-hidden min-h-0">
        <div className="flex items-center gap-3 shrink-0">
          <Briefcase className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-2xl font-bold leading-tight">Key Companies</h2>
            <p className="text-xs text-muted-foreground">
              Weekly cross-domain technical and business updates for the
              companies you care about.
            </p>
          </div>
        </div>
        <div className="flex-1 overflow-auto min-h-0">
          <KeyCompaniesView />
        </div>
      </div>
    </div>
  );
};

export default KeyCompaniesPage;
