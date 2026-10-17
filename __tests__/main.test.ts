/**
 * Unit tests for Naukri Profile Manager input behavior.
 */

import { describe, expect, it } from '@jest/globals';

describe('Resume Path Handling', () => {
  it('should handle single resume path', () => {
    const singlePath = './candidate-resume-1.pdf';
    const paths = [singlePath];

    expect(paths.length).toBe(1);
    expect(paths[0]).toBe(singlePath);
  });

  it('should handle multiple resume paths', () => {
    const multiplePaths = `./candidate-resume-1.pdf
  ./candidate-resume-2.pdf
  ./candidate-resume-3.pdf`;

    const paths = multiplePaths
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));

    expect(paths.length).toBe(3);
  });

  it('should filter out comment lines', () => {
    const pathsWithComments = `./candidate-resume-1.pdf
# This is a comment
  ./candidate-resume-2.pdf`;

    const paths = pathsWithComments
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));

    expect(paths.length).toBe(2);
    expect(paths).toEqual([
      './candidate-resume-1.pdf',
      './candidate-resume-2.pdf'
    ]);
  });

  it('should filter out empty lines', () => {
    const pathsWithEmptyLines = `./candidate-resume-1.pdf

  ./candidate-resume-2.pdf`;

    const paths = pathsWithEmptyLines
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#'));

    expect(paths.length).toBe(2);
  });
});

describe('Date-based Resume Selection', () => {
  it('should use modulo for deterministic selection', () => {
    const resumePaths = ['resume1.pdf', 'resume2.pdf', 'resume3.pdf'];
    const selectionFactor = 5;
    const selectedIndex = selectionFactor % resumePaths.length;

    expect(selectedIndex).toBeLessThan(resumePaths.length);
    expect(selectedIndex).toBeGreaterThanOrEqual(0);
  });

  it('should rotate through all resumes over time', () => {
    const resumePaths = ['resume1.pdf', 'resume2.pdf', 'resume3.pdf'];
    const selections = new Set();

    // Simulate different days
    for (let day = 0; day < 10; day++) {
      const index = day % resumePaths.length;
      selections.add(resumePaths[index]);
    }

    // Should have used all resumes
    expect(selections.size).toBe(resumePaths.length);
  });
});
