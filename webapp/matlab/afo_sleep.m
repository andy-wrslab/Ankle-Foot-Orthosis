function out = afo_sleep(s)
%AFO_SLEEP Test helper: block for s seconds (used to test the worker timeout).
pause(s);
out = 'done';
end
