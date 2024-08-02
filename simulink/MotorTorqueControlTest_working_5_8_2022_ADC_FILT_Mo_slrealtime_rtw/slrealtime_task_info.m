function [taskInfo, numtask, isDeploymentDiagram]=slrealtime_task_info()
   taskInfo(1).samplePeriod = 0.001;
   taskInfo(1).sampleOffset = 0.0;
   taskInfo(1).taskPrio = 11;
   taskInfo(1).taskName = 'BaseRate';
   taskInfo(1).entryPoints = {};
   taskInfo(2).samplePeriod = 0.005;
   taskInfo(2).sampleOffset = 0.0;
   taskInfo(2).taskPrio = 10;
   taskInfo(2).taskName = ['SubRate' '1'];        
   taskInfo(2).entryPoints = {};
   taskInfo(3).samplePeriod = 0.01;
   taskInfo(3).sampleOffset = 0.0;
   taskInfo(3).taskPrio = 9;
   taskInfo(3).taskName = ['SubRate' '2'];        
   taskInfo(3).entryPoints = {};
   numtask = 3;
   for i = 1:numtask
      if ( 0 == isnumeric(taskInfo(i).samplePeriod) )
         taskInfo(i).samplePeriod = evalin('base', taskInfo(i).samplePeriod);
      end
      if ( isempty(taskInfo(i).taskName) )
         taskInfo(i).taskName = ['AutoGen' i ];
      end
   end
   isDeploymentDiagram = 0;
end 
