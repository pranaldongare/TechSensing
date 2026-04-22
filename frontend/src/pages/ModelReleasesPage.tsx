import React from 'react';
import { Cpu } from 'lucide-react';
import AppNavbar from '@/components/AppNavbar';
import ModelReleasesView from '@/components/ModelReleasesView';

const ModelReleasesPage: React.FC = () => {
  return (
    <div className="h-screen flex flex-col">
      <AppNavbar />
      <div className="flex-1 flex flex-col p-6 gap-4 overflow-hidden min-h-0">
        <div className="flex items-center gap-3 shrink-0">
          <Cpu className="w-6 h-6 text-primary" />
          <div>
            <h2 className="text-2xl font-bold leading-tight">Model Releases</h2>
            <p className="text-xs text-muted-foreground">
              Latest AI model releases from Artificial Analysis and HuggingFace.
            </p>
          </div>
        </div>
        <div className="flex-1 overflow-auto min-h-0">
          <ModelReleasesView />
        </div>
      </div>
    </div>
  );
};

export default ModelReleasesPage;
