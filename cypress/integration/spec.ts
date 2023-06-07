it('can access top page', () => {
  cy.visit('/');
  cy.contains('実行ログ');
});
